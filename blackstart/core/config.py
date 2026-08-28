"""Typed configuration for the BLACKSTART simulation kernel.

Configuration is loaded from the YAML files in ``configs/`` into frozen Pydantic
models. Two properties matter here:

1. **Validation at the boundary.** Physically incoherent configuration (a safe
   level above the overflow height, an unstable timestep, a backstop threshold
   looser than the invariant it claims to protect) is rejected at load time
   rather than producing a quietly wrong experiment.
2. **Canonical hashing.** :func:`configuration_hash` produces a stable SHA-256
   over the fully resolved configuration. That hash is recorded in every
   evidence manifest, so a result can never be silently attributed to a
   configuration that did not produce it (ADR-005).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ArchitectureConfig",
    "BackstopConfig",
    "BlackstartConfig",
    "ConsequencesConfig",
    "InvariantSpec",
    "InvariantsConfig",
    "ProcessConfig",
    "configuration_hash",
    "load_config",
]

# The Euler integration timestep must be far below the dominant process time
# constant. A ratio of 20 is a conservative floor; BLACKSTART's shipped
# configuration runs at roughly 780 (ADR-002).
_MIN_TIME_CONSTANT_RATIO = 20.0

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


class _Frozen(BaseModel):
    """Base for immutable configuration models with strict field checking."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Process configuration
# ---------------------------------------------------------------------------


class SimulationConfig(_Frozen):
    """Integration parameters for the discrete-time kernel."""

    timestep_s: float = Field(gt=0.0, le=5.0)
    gravity_m_s2: float = Field(gt=0.0)


class TankConfig(_Frozen):
    """Geometry and initial condition of the storage tank."""

    area_m2: float = Field(gt=0.0)
    overflow_height_m: float = Field(gt=0.0)
    initial_level_m: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _initial_level_within_tank(self) -> Self:
        if self.initial_level_m > self.overflow_height_m:
            msg = (
                f"initial_level_m ({self.initial_level_m}) exceeds "
                f"overflow_height_m ({self.overflow_height_m})"
            )
            raise ValueError(msg)
        return self


class SourceConfig(_Frozen):
    """Upstream supply reservoir feeding the pump suction."""

    initial_level_m: float = Field(ge=0.0)
    suction_limit_m: float = Field(ge=0.0)


class PumpConfig(_Frozen):
    """Linear pump curve parameters."""

    nominal_flow_m3_s: float = Field(gt=0.0)
    shutoff_head_m: float = Field(gt=0.0)
    initial_state: Literal["on", "off"]


class ValveConfig(_Frozen):
    """Throttling outlet valve parameters."""

    discharge_coefficient: float = Field(gt=0.0, le=1.0)
    orifice_area_m2: float = Field(gt=0.0)
    initial_position: float = Field(ge=0.0, le=1.0)
    max_slew_per_s: float = Field(gt=0.0)


class DemandConfig(_Frozen):
    """Synthetic downstream consumption."""

    base_rate_m3_s: float = Field(gt=0.0)
    variation_fraction: float = Field(ge=0.0, lt=1.0)


class ReserveProtectionConfig(_Frozen):
    """Outlet-throttling policy that defends the operational reserve."""

    engage_level_m: float = Field(gt=0.0)
    release_level_m: float = Field(gt=0.0)
    throttled_position: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _hysteresis_ordered(self) -> Self:
        if self.release_level_m <= self.engage_level_m:
            msg = "reserve protection release level must be above the engage level"
            raise ValueError(msg)
        return self


class ControlConfig(_Frozen):
    """Hysteresis level-control parameters."""

    operator_setpoint_m: float = Field(gt=0.0)
    deadband_m: float = Field(gt=0.0)
    scan_interval_s: float = Field(gt=0.0)
    min_run_time_s: float = Field(ge=0.0)
    min_off_time_s: float = Field(ge=0.0)
    reserve_protection: ReserveProtectionConfig

    @property
    def band_lower_m(self) -> float:
        """Level at or below which the pump is commanded to run."""
        return self.operator_setpoint_m - self.deadband_m

    @property
    def band_upper_m(self) -> float:
        """Level at or above which the pump is commanded to stop."""
        return self.operator_setpoint_m + self.deadband_m


class LevelTransmitterConfig(_Frozen):
    """Operator-facing level transmitter characteristics."""

    noise_std_m: float = Field(ge=0.0)
    resolution_m: float = Field(gt=0.0)


class FlowMeterConfig(_Frozen):
    """Flow instrument characteristics."""

    noise_std_m3_s: float = Field(ge=0.0)


class SensorsConfig(_Frozen):
    """Instrumentation reporting the process to the control system."""

    level_transmitter: LevelTransmitterConfig
    flow_meter: FlowMeterConfig


class IndependentElementConfig(_Frozen):
    """Independent level element used solely by the engineering backstop.

    Modelled as a separate hardwired channel unaffected by ``sensor.*`` scenario
    effects. That independence is an explicit modelling assumption, not a proven
    property; see ``docs/limitations.md``.
    """

    noise_std_m: float = Field(ge=0.0)
    resolution_m: float = Field(gt=0.0)


class ProcessConfig(_Frozen):
    """Complete physical process configuration (``configs/process.yaml``)."""

    schema_version: int
    process_id: str
    description: str
    simulation: SimulationConfig
    tank: TankConfig
    source: SourceConfig
    pump: PumpConfig
    valve: ValveConfig
    demand: DemandConfig
    control: ControlConfig
    sensors: SensorsConfig
    independent_level_element: IndependentElementConfig

    @property
    def dominant_time_constant_s(self) -> float:
        """Dominant tank filling time constant ``A * H_shutoff / q_nominal`` in seconds."""
        return self.tank.area_m2 * self.pump.shutoff_head_m / self.pump.nominal_flow_m3_s

    @model_validator(mode="after")
    def _timestep_is_stable(self) -> Self:
        ratio = self.dominant_time_constant_s / self.simulation.timestep_s
        if ratio < _MIN_TIME_CONSTANT_RATIO:
            msg = (
                f"timestep_s={self.simulation.timestep_s} is too coarse: "
                f"time-constant ratio {ratio:.1f} is below the required "
                f"{_MIN_TIME_CONSTANT_RATIO}. Explicit Euler would be unstable."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _control_band_is_physical(self) -> Self:
        if self.control.band_lower_m <= 0.0:
            msg = "control deadband places the lower band edge at or below empty"
            raise ValueError(msg)
        if self.control.band_upper_m >= self.tank.overflow_height_m:
            msg = "control deadband places the upper band edge at or above overflow"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Invariant configuration
# ---------------------------------------------------------------------------


class InvariantSpec(_Frozen):
    """Declarative specification of one safety or mission invariant.

    Field applicability depends on ``kind``; unused numeric fields stay ``None``.
    The concrete evaluator classes in :mod:`blackstart.core.invariants.water`
    consume the fields relevant to their kind.
    """

    id: str = Field(pattern=r"^INV-\d{3}$")
    name: str
    kind: Literal[
        "instantaneous_upper_bound",
        "temporal_lower_bound",
        "conditional",
        "rate",
        "control_bound",
        "cross_view",
    ]
    rationale: str
    observes: str | list[str]
    tolerance_s: float = Field(ge=0.0)
    severity_on_violation: str = Field(pattern=r"^C[0-5]$")

    limit_m: float | None = None
    margin_m: float | None = None
    condition: str | None = None
    max_setpoint_slew_m_s: float | None = None
    max_pump_starts_per_hour: float | None = None
    min_effective_setpoint_m: float | None = None
    max_effective_setpoint_m: float | None = None
    max_divergence_m: float | None = None


class InvariantsConfig(_Frozen):
    """Complete invariant configuration (``configs/invariants.yaml``)."""

    schema_version: int
    invariants: list[InvariantSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_unique(self) -> Self:
        ids = [spec.id for spec in self.invariants]
        if len(ids) != len(set(ids)):
            msg = f"duplicate invariant ids: {ids}"
            raise ValueError(msg)
        return self

    def by_id(self, invariant_id: str) -> InvariantSpec:
        """Return the specification for ``invariant_id``.

        Raises:
            KeyError: if no invariant with that identifier is configured.
        """
        for spec in self.invariants:
            if spec.id == invariant_id:
                return spec
        msg = f"unknown invariant id: {invariant_id}"
        raise KeyError(msg)


# ---------------------------------------------------------------------------
# Consequence configuration
# ---------------------------------------------------------------------------


class CriticalFunctionConfig(_Frozen):
    """Definition of the critical function the range is defending."""

    id: str = Field(pattern=r"^CF-\d{3}$")
    statement: str
    satisfied_when: list[str]


class NormalBandConfig(_Frozen):
    """Normal operating band for the tank level."""

    lower_m: float
    upper_m: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.lower_m >= self.upper_m:
            msg = "normal_band lower_m must be strictly below upper_m"
            raise ValueError(msg)
        return self


class ConsequenceSpec(_Frozen):
    """One consequence severity class and the conditions that produce it."""

    level: str = Field(pattern=r"^C[0-5]$")
    name: str
    description: str
    # The condition tree is documentation of the classifier's intent. The
    # classifier itself is explicit typed code, not a rule interpreter: safety
    # classification logic should be readable and directly unit-testable rather
    # than assembled at runtime. Consistency between the two is asserted by
    # tests/unit/test_consequence_config_alignment.py.
    conditions: dict[str, Any]


class ConsequencesConfig(_Frozen):
    """Complete consequence taxonomy (``configs/consequences.yaml``)."""

    schema_version: int
    critical_function: CriticalFunctionConfig
    normal_band: NormalBandConfig
    consequences: list[ConsequenceSpec] = Field(min_length=1)

    # Quantitative thresholds consumed by the classifier. Kept as named
    # constants rather than parsed from the condition tree so that the numbers
    # governing safety classification are visible in one place.
    degradation_shortfall_ratio: float = 0.10
    degradation_sustained_s: float = 60.0
    loss_shortfall_ratio: float = 0.50
    loss_sustained_s: float = 60.0
    minor_shortfall_ratio: float = 0.02
    catastrophic_spill_m3: float = 20.0
    catastrophic_unsafe_s: float = 300.0

    @model_validator(mode="after")
    def _levels_complete_and_ordered(self) -> Self:
        levels = [spec.level for spec in self.consequences]
        if levels != sorted(levels):
            msg = f"consequence classes must be listed in ascending order: {levels}"
            raise ValueError(msg)
        if len(levels) != len(set(levels)):
            msg = f"duplicate consequence classes: {levels}"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Architecture configuration
# ---------------------------------------------------------------------------


class ZoneConfig(_Frozen):
    """One security zone in the system-of-systems architecture."""

    id: str
    name: str
    network: str
    purpose: str
    trust: str


class ServiceConfig(_Frozen):
    """One deployed service and its zone-network attachments."""

    id: str
    zone: str
    networks: list[str] = Field(min_length=1)
    role: str
    publishes: list[str]


class ConduitConfig(_Frozen):
    """One permitted cross-zone communication path."""

    id: str = Field(pattern=r"^CDT-\d{3}$")
    from_zone: str
    to_zone: str
    initiator: str
    responder: str
    protocol: str
    port: int = Field(gt=0, lt=65536)
    direction: str
    data: str


class BackstopRuleConfig(_Frozen):
    """One rule enforced by the engineering backstop."""

    id: str = Field(pattern=r"^BS-\d{2}$")
    name: str
    description: str
    protects: list[str]

    setpoint_min_m: float | None = None
    setpoint_max_m: float | None = None
    max_slew_m_s: float | None = None
    trip_level_m: float | None = None
    reset_level_m: float | None = None
    min_off_time_s: float | None = None


class BackstopIndependenceConfig(_Frozen):
    """Prose statement of what "independent" means for this backstop."""

    command_path: str
    measurement: str
    limits: str


class BackstopConfig(_Frozen):
    """Engineering backstop definition (``configs/architecture.yaml``)."""

    id: str
    name: str
    enabled_by_default: bool
    independence: BackstopIndependenceConfig
    rules: list[BackstopRuleConfig] = Field(min_length=1)

    def rule(self, rule_id: str) -> BackstopRuleConfig:
        """Return the rule with identifier ``rule_id``.

        Raises:
            KeyError: if no such rule is configured.
        """
        for item in self.rules:
            if item.id == rule_id:
                return item
        msg = f"unknown backstop rule: {rule_id}"
        raise KeyError(msg)


class ArchitectureConfig(_Frozen):
    """Complete architecture configuration (``configs/architecture.yaml``)."""

    schema_version: int
    zones: list[ZoneConfig] = Field(min_length=1)
    permitted_adjacency: list[list[str]]
    forbidden_adjacency: list[list[str]]
    services: list[ServiceConfig] = Field(min_length=1)
    conduits: list[ConduitConfig] = Field(min_length=1)
    backstop: BackstopConfig

    @model_validator(mode="after")
    def _services_reference_known_zones(self) -> Self:
        zone_ids = {zone.id for zone in self.zones}
        networks = {zone.network for zone in self.zones}
        for service in self.services:
            if service.zone not in zone_ids:
                msg = f"service {service.id} references unknown zone {service.zone}"
                raise ValueError(msg)
            unknown = set(service.networks) - networks
            if unknown:
                msg = f"service {service.id} references unknown networks {sorted(unknown)}"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _no_service_bridges_forbidden_zones(self) -> Self:
        network_to_zone = {zone.network: zone.id for zone in self.zones}
        forbidden = {tuple(sorted(pair)) for pair in self.forbidden_adjacency}
        for service in self.services:
            attached = sorted({network_to_zone[net] for net in service.networks})
            for i, left in enumerate(attached):
                for right in attached[i + 1 :]:
                    if (left, right) in forbidden:
                        msg = f"service {service.id} bridges forbidden zone pair ({left}, {right})"
                        raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


class BlackstartConfig(_Frozen):
    """The fully resolved configuration for one experiment."""

    process: ProcessConfig
    invariants: InvariantsConfig
    consequences: ConsequencesConfig
    architecture: ArchitectureConfig

    @model_validator(mode="after")
    def _backstop_is_tighter_than_invariants(self) -> Self:
        """Reject a backstop that cannot act before the safety limit it protects.

        A trip level at or above the INV-001 limit would let the process reach an
        unsafe state before the constraint engaged, making the control decorative.
        """
        trip = self.architecture.backstop.rule("BS-03").trip_level_m
        limit = self.invariants.by_id("INV-001").limit_m
        if trip is None or limit is None:
            msg = "BS-03 trip_level_m and INV-001 limit_m must both be configured"
            raise ValueError(msg)
        if trip >= limit:
            msg = (
                f"backstop trip level ({trip} m) must be strictly below the "
                f"INV-001 safe limit ({limit} m); otherwise the constraint "
                f"cannot act before the safety limit is breached"
            )
            raise ValueError(msg)

        clamp = self.architecture.backstop.rule("BS-01").setpoint_max_m
        if clamp is None:
            msg = "BS-01 setpoint_max_m must be configured"
            raise ValueError(msg)
        # The clamped setpoint plus the control deadband must still land below
        # the safe limit, or the clamp alone would not hold the process safe.
        reachable = clamp + self.process.control.deadband_m
        if reachable >= limit:
            msg = (
                f"clamped setpoint ({clamp} m) plus deadband "
                f"({self.process.control.deadband_m} m) reaches {reachable} m, "
                f"at or above the INV-001 limit ({limit} m)"
            )
            raise ValueError(msg)

        setpoint_bound = self.invariants.by_id("INV-005")
        clamp_min = self.architecture.backstop.rule("BS-01").setpoint_min_m
        if (
            setpoint_bound.min_effective_setpoint_m != clamp_min
            or setpoint_bound.max_effective_setpoint_m != clamp
        ):
            msg = (
                "INV-005 effective-setpoint bounds must exactly match the BS-01 "
                "engineering envelope; enforcement and verification cannot drift"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _safe_limit_below_overflow(self) -> Self:
        limit = self.invariants.by_id("INV-001").limit_m
        if limit is None or limit >= self.process.tank.overflow_height_m:
            msg = (
                "INV-001 limit must be strictly below the tank overflow height so "
                "that a safety excursion is representable rather than clamped"
            )
            raise ValueError(msg)
        return self


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML document into a mapping.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the document does not contain a top-level mapping.
    """
    if not path.is_file():
        msg = f"configuration file not found: {path}"
        raise FileNotFoundError(msg)
    # safe_load never constructs arbitrary Python objects.
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        msg = f"expected a YAML mapping at the top level of {path}"
        raise ValueError(msg)
    return loaded


def load_config(config_dir: Path | None = None) -> BlackstartConfig:
    """Load and cross-validate the complete BLACKSTART configuration.

    Args:
        config_dir: Directory holding the four configuration documents. Defaults
            to the repository's ``configs/`` directory.

    Returns:
        The validated, immutable aggregate configuration.
    """
    directory = config_dir if config_dir is not None else DEFAULT_CONFIG_DIR
    return BlackstartConfig(
        process=ProcessConfig.model_validate(_read_yaml(directory / "process.yaml")),
        invariants=InvariantsConfig.model_validate(_read_yaml(directory / "invariants.yaml")),
        consequences=ConsequencesConfig.model_validate(_read_yaml(directory / "consequences.yaml")),
        architecture=ArchitectureConfig.model_validate(_read_yaml(directory / "architecture.yaml")),
    )


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` to a byte-stable canonical JSON string.

    Keys are sorted and separators are fixed, so the output depends only on the
    data. This is the serialisation used for configuration hashing and for every
    evidence artefact, so that identical runs produce identical bytes (ADR-005).
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def configuration_hash(config: BlackstartConfig, extra: dict[str, Any] | None = None) -> str:
    """Compute the SHA-256 configuration hash recorded in evidence manifests.

    Args:
        config: The resolved configuration.
        extra: Additional resolved inputs that affect the experiment outcome,
            such as the scenario definition and variant overrides. Included in
            the hash so that a variant cannot be confused with its baseline.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    payload: dict[str, Any] = {"config": config.model_dump(mode="json")}
    if extra:
        payload["extra"] = extra
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
