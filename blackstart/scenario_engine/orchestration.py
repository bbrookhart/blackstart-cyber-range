"""Experiment orchestration: the deterministic scan loop.

One fixed scan order per timestep, with no wall-clock read and no I/O anywhere
inside it:

.. code-block:: text

    t -> scenario effects
      -> sense (truth to reported)
      -> control scan
      -> engineering backstop
      -> actuate
      -> record state, invariants, consequence
      -> integrate physics to t + dt

Everything recorded at ``t`` is the state at ``t``: the reported view is sampled
from the truth at ``t``, the command computed at ``t`` drives the interval
``[t, t + dt)``, and the flows recorded at ``t`` are those integrated over the
preceding interval. Keeping that consistent is what makes the process trace
readable as a single coherent timeline.

Experiment identifiers are **deterministic**, derived from the scenario, variant,
seed and configuration hash. Re-running the same experiment therefore reproduces
the evidence package byte-for-byte, including the identifier embedded in every
event (ADR-005).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from blackstart import __version__
from blackstart.controller.backstop import EngineeringBackstop
from blackstart.controller.control_logic import LevelController
from blackstart.controller.plc_sim import PlcScanner
from blackstart.core.config import BlackstartConfig, configuration_hash
from blackstart.core.consequence.classifier import ConsequenceClassifier, ConsequenceSummary
from blackstart.core.invariants.engine import InvariantEngine
from blackstart.core.models import (
    CommandState,
    ConsequenceLevel,
    InvariantStatus,
    ProcessState,
)
from blackstart.core.physics.process import WaterProcessModel
from blackstart.core.physics.sensors import DemandModel, SensorModel
from blackstart.scenario_engine.effects import EffectContext, SetpointHolder, resolve_effect
from blackstart.scenario_engine.schema import Scenario, ScenarioEvent
from blackstart.telemetry.events import Event, EventBus, EventType, Severity, Zone
from blackstart.telemetry.exporters.csv_exporter import ProcessTraceRow, ProcessTraceWriter

__all__ = [
    "VARIANTS",
    "ExperimentResult",
    "ExperimentRunner",
    "Variant",
    "resolve_variant",
]

#: Interval at which periodic process telemetry is emitted to the event stream.
#: The full per-timestep trace lives in ``process.csv``; the event stream carries
#: a sampled trend plus every state change, which keeps it readable.
_TELEMETRY_INTERVAL_S = 10.0

_ASSET_CONTROLLER = "PLC-001"
_ASSET_TANK = "TNK-001"
_ASSET_PUMP = "PMP-001"
_ASSET_BACKSTOP = "EBS-001"
_ASSET_LEVEL_TX = "LIT-001"


@dataclass(frozen=True, slots=True)
class Variant:
    """One configuration of an experiment.

    v0.1 defines exactly two, differing in a single respect: whether the
    engineering backstop is present. A clean single-variable comparison is the
    whole basis of the flagship result.
    """

    name: str
    backstop_enabled: bool
    description: str


VARIANTS: dict[str, Variant] = {
    "backstop-disabled": Variant(
        name="backstop-disabled",
        backstop_enabled=False,
        description="Control case. No independent engineering constraint on commands.",
    ),
    "backstop-enabled": Variant(
        name="backstop-enabled",
        backstop_enabled=True,
        description="Independent engineering constraint EBS-001 active.",
    ),
}


def resolve_variant(name: str) -> Variant:
    """Look up an experiment variant by name.

    Raises:
        ValueError: if the variant is not defined.
    """
    variant = VARIANTS.get(name)
    if variant is None:
        known = ", ".join(sorted(VARIANTS))
        msg = f"unknown variant '{name}'. Known variants: {known}"
        raise ValueError(msg)
    return variant


@dataclass(slots=True)
class _ScheduledEffect:
    """Runtime state of one scenario event.

    ``params`` is a deep copy of the scenario's parameters. Effects record
    restore values into it, and the scenario object must not be polluted across
    runs -- ``experiment compare`` executes the same scenario twice in one
    process, so a shared mutable dict would silently break the comparison.
    """

    event: ScenarioEvent
    params: dict[str, Any]
    activated: bool = False
    deactivated: bool = False


@dataclass(slots=True)
class ExperimentResult:
    """Everything one experiment produced."""

    experiment_id: str
    scenario: Scenario
    variant: Variant
    seed: int
    blackstart_version: str
    configuration_hash: str
    duration_s: float
    timestep_s: float
    step_count: int
    trace: ProcessTraceWriter
    events: EventBus
    invariants: dict[str, Any]
    consequences: ConsequenceSummary
    backstop: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def maximum_consequence(self) -> ConsequenceLevel:
        """Highest consequence class reached during the experiment."""
        return self.consequences.maximum_level

    @property
    def violated_invariants(self) -> list[str]:
        """Identifiers of invariants violated at least once."""
        violated = self.invariants["violated_invariants"]
        return list(violated)


class ExperimentRunner:
    """Executes one scenario under one variant, deterministically."""

    def __init__(
        self,
        config: BlackstartConfig,
        scenario: Scenario,
        variant: Variant,
        *,
        seed_override: int | None = None,
    ) -> None:
        """Build a runner for one experiment.

        Args:
            config: Resolved BLACKSTART configuration.
            scenario: The scenario to execute.
            variant: The experiment variant (backstop enabled or disabled).
            seed_override: Replace the scenario's seed. Used for seed-sensitivity
                studies; recorded in the manifest so the result stays traceable.
        """
        self._config = config
        self._scenario = scenario
        self._variant = variant
        self._seed = scenario.seed if seed_override is None else seed_override

        # The code version participates in the hash: a result is a function of
        # (version, configuration, seed), so two releases must not be able to
        # claim the same experiment identifier for different behaviour (ADR-005).
        self._config_hash = configuration_hash(
            config,
            extra={
                "scenario": scenario.causal_fingerprint(),
                "variant": variant.name,
                "seed": self._seed,
                "blackstart_version": __version__,
            },
        )
        self._experiment_id = (
            f"EXP-{scenario.id.replace('-', '')}-{variant.name}-{self._config_hash[:8]}"
        )

    @property
    def experiment_id(self) -> str:
        """Deterministic identifier for this experiment."""
        return self._experiment_id

    @property
    def configuration_hash(self) -> str:
        """SHA-256 over the fully resolved configuration, scenario and variant."""
        return self._config_hash

    def run(self) -> ExperimentResult:
        """Execute the experiment and return its complete result."""
        process_config = self._config.process
        dt_s = process_config.simulation.timestep_s
        step_count = round(self._scenario.duration_s / dt_s)

        # The single source of randomness for the entire experiment.
        rng = Random(self._seed)  # noqa: S311 - simulation variation, not cryptography

        physics = WaterProcessModel(process_config)
        sensors = SensorModel(process_config, rng)
        demand_model = DemandModel(process_config, rng)
        controller = LevelController(process_config)
        scanner = PlcScanner(controller, process_config.control.scan_interval_s)
        backstop = EngineeringBackstop(
            self._config.architecture.backstop,
            process_config,
            enabled=self._variant.backstop_enabled,
        )
        # Fresh per experiment: both carry accumulated temporal state (ADR-004).
        invariant_engine = InvariantEngine(self._config.invariants, process_config)
        classifier = ConsequenceClassifier(self._config.consequences)

        truth = physics.initial_state()
        setpoint = SetpointHolder(requested_m=process_config.control.operator_setpoint_m)
        ctx = EffectContext(demand=demand_model, sensors=sensors, truth=truth, setpoint=setpoint)
        scheduled = [
            _ScheduledEffect(event=event, params=copy.deepcopy(event.params))
            for event in self._scenario.events
        ]

        events = EventBus()
        trace = ProcessTraceWriter()

        events.emit(
            Event(
                t_s=0.0,
                experiment_id=self._experiment_id,
                source="scenario-engine",
                zone=Zone.RANGE,
                event_type=EventType.EXPERIMENT_LIFECYCLE,
                asset_id=self._experiment_id,
                severity=Severity.INFO,
                data={
                    "phase": "start",
                    "scenario_id": self._scenario.id,
                    "variant": self._variant.name,
                    "backstop_enabled": self._variant.backstop_enabled,
                    "seed": self._seed,
                    "duration_s": self._scenario.duration_s,
                    "timestep_s": dt_s,
                    "blackstart_version": __version__,
                    "configuration_hash": self._config_hash,
                },
            )
        )

        previous_consequence: ConsequenceLevel | None = None
        previous_invariant_status: dict[str, InvariantStatus] = {}
        previous_pump_energised = truth.pump_energised
        previous_supervisory = True
        previous_reserve_protection = False
        next_telemetry_t_s = 0.0

        for step in range(step_count):
            t_s = step * dt_s

            self._apply_scenario_effects(scheduled, ctx, t_s, dt_s, events)

            reported = sensors.read(truth)
            independent_level_m = sensors.read_independent_element(truth)
            demand_m3_s = demand_model.sample()

            # Stage one: constrain the setpoint BEFORE the controller forms a
            # request, so the controller never pursues an out-of-range target.
            constraint = backstop.constrain_setpoint(setpoint.requested_m, dt_s)
            request = scanner.execute(reported, constraint.effective_setpoint_m, t_s)
            # Stage two: apply the actuator interlocks to the formed request.
            decision = backstop.evaluate_permissive(
                request,
                constraint,
                independent_level_m=independent_level_m,
                source_level_m=truth.source_level_m,
                t_s=t_s,
            )
            if request.pump_run and not decision.pump_permitted:
                controller.notify_pump_denied(t_s)

            # Actuate. The command applied at t drives the interval [t, t + dt).
            truth.pump_energised = decision.pump_permitted
            truth.valve_position = physics.slew_valve(
                truth.valve_position, decision.valve_position, dt_s
            )

            command = CommandState(
                requested_setpoint_m=setpoint.requested_m,
                effective_setpoint_m=decision.effective_setpoint_m,
                pump_permissive=decision.pump_permitted,
                pump_command=request.pump_run,
                valve_command=decision.valve_position,
                pump_starts=controller.pump_starts,
                backstop_actions=list(decision.constrained_by + decision.denied_by),
            )
            state = ProcessState(
                t_s=t_s,
                truth=truth,
                reported=reported,
                command=command,
                independent_level_m=independent_level_m,
            )

            invariant_result = invariant_engine.evaluate(state, dt_s)
            consequence = classifier.classify(state, invariant_result, dt_s)

            # --- Event emission: state changes, plus a sampled trend ----------
            if truth.pump_energised != previous_pump_energised:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="controller-01",
                        zone=Zone.CONTROL,
                        event_type=EventType.CONTROL_COMMAND,
                        asset_id=_ASSET_PUMP,
                        severity=Severity.INFO,
                        data={
                            "pump_energised": truth.pump_energised,
                            "reported_level_m": round(reported.tank_level_m, 4),
                            "effective_setpoint_m": round(decision.effective_setpoint_m, 4),
                            "pump_starts": controller.pump_starts,
                        },
                    )
                )
                previous_pump_energised = truth.pump_energised

            if decision.acted:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="backstop-01",
                        zone=Zone.CONTROL,
                        event_type=EventType.CONTROL_BACKSTOP,
                        asset_id=_ASSET_BACKSTOP,
                        severity=Severity.WARNING if decision.denied_by else Severity.NOTICE,
                        data={
                            "constrained_by": list(decision.constrained_by),
                            "denied_by": list(decision.denied_by),
                            "requested_setpoint_m": round(setpoint.requested_m, 4),
                            "effective_setpoint_m": round(decision.effective_setpoint_m, 4),
                            "independent_level_m": round(independent_level_m, 4),
                        },
                    )
                )

            for sample in invariant_result.samples:
                previous = previous_invariant_status.get(sample.invariant_id)
                if previous is not sample.status:
                    events.emit(
                        Event(
                            t_s=t_s,
                            experiment_id=self._experiment_id,
                            source="invariant-engine",
                            zone=Zone.RANGE,
                            event_type=EventType.INVARIANT_STATE,
                            asset_id=sample.invariant_id,
                            severity=_invariant_severity(sample.status),
                            data={
                                "status": sample.status.value,
                                "previous_status": None if previous is None else previous.value,
                                "value": round(sample.value, 6),
                                "limit": sample.limit,
                                "detail": {
                                    k: round(v, 6) for k, v in sorted(sample.detail.items())
                                },
                            },
                        )
                    )
                    previous_invariant_status[sample.invariant_id] = sample.status

            if consequence.level is not previous_consequence:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="consequence-classifier",
                        zone=Zone.RANGE,
                        event_type=EventType.CONSEQUENCE_CHANGE,
                        asset_id="CF-001",
                        severity=_consequence_severity(consequence.level),
                        data={
                            "level": consequence.level.value,
                            "previous_level": None
                            if previous_consequence is None
                            else previous_consequence.value,
                            "drivers": list(consequence.drivers),
                        },
                    )
                )
                previous_consequence = consequence.level

            if reported.supervisory_available != previous_supervisory:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="hmi-01",
                        zone=Zone.OT,
                        event_type=EventType.SERVICE_STATE,
                        asset_id="HMI-001",
                        severity=Severity.WARNING
                        if not reported.supervisory_available
                        else Severity.NOTICE,
                        data={"supervisory_available": reported.supervisory_available},
                    )
                )
                previous_supervisory = reported.supervisory_available

            if request.reserve_protection_active != previous_reserve_protection:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="controller-01",
                        zone=Zone.CONTROL,
                        event_type=EventType.RECOVERY_ACTION,
                        asset_id="VLV-001",
                        severity=Severity.NOTICE,
                        data={
                            "action": "reserve_protection",
                            "active": request.reserve_protection_active,
                            "valve_position": round(request.valve_position, 4),
                            "reported_level_m": round(reported.tank_level_m, 4),
                        },
                    )
                )
                previous_reserve_protection = request.reserve_protection_active

            if t_s + 1e-9 >= next_telemetry_t_s:
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="historian-01",
                        zone=Zone.OT,
                        event_type=EventType.PROCESS_TELEMETRY,
                        asset_id=_ASSET_TANK,
                        severity=Severity.INFO,
                        data={
                            "true_tank_level_m": round(truth.tank_level_m, 4),
                            "reported_tank_level_m": round(reported.tank_level_m, 4),
                            "true_inflow_m3_s": round(truth.inflow_m3_s, 6),
                            "true_outflow_m3_s": round(truth.outflow_m3_s, 6),
                            "demand_m3_s": round(truth.demand_m3_s, 6),
                            "service_shortfall_ratio": round(truth.service_shortfall_ratio, 6),
                            "consequence_level": consequence.level.value,
                        },
                    )
                )
                next_telemetry_t_s = t_s + _TELEMETRY_INTERVAL_S

            trace.append(
                ProcessTraceRow(
                    t_s=t_s,
                    true_tank_level_m=truth.tank_level_m,
                    reported_tank_level_m=reported.tank_level_m,
                    independent_level_m=independent_level_m,
                    true_source_level_m=truth.source_level_m,
                    true_inflow_m3_s=truth.inflow_m3_s,
                    true_outflow_m3_s=truth.outflow_m3_s,
                    demand_m3_s=truth.demand_m3_s,
                    service_shortfall_ratio=truth.service_shortfall_ratio,
                    spill_volume_m3=truth.spill_volume_m3,
                    pump_energised=int(truth.pump_energised),
                    pump_permitted=int(decision.pump_permitted),
                    valve_position=truth.valve_position,
                    requested_setpoint_m=setpoint.requested_m,
                    effective_setpoint_m=decision.effective_setpoint_m,
                    supervisory_available=int(reported.supervisory_available),
                    consequence_level=consequence.level.value,
                    violated_invariants="|".join(sorted(invariant_result.violated_ids)),
                )
            )

            physics.step(truth, demand_m3_s, dt_s)

        final_t_s = step_count * dt_s
        invariants_summary = invariant_engine.summary(final_t_s)
        consequence_summary = classifier.summary()

        events.emit(
            Event(
                t_s=final_t_s,
                experiment_id=self._experiment_id,
                source="scenario-engine",
                zone=Zone.RANGE,
                event_type=EventType.EXPERIMENT_LIFECYCLE,
                asset_id=self._experiment_id,
                severity=Severity.INFO,
                data={
                    "phase": "end",
                    "steps": step_count,
                    "maximum_consequence": consequence_summary.maximum_level.value,
                    "violated_invariants": invariants_summary["violated_invariants"],
                    "control_scans": scanner.scan_count,
                    "pump_starts": controller.pump_starts,
                },
            )
        )

        return ExperimentResult(
            experiment_id=self._experiment_id,
            scenario=self._scenario,
            variant=self._variant,
            seed=self._seed,
            blackstart_version=__version__,
            configuration_hash=self._config_hash,
            duration_s=self._scenario.duration_s,
            timestep_s=dt_s,
            step_count=step_count,
            trace=trace,
            events=events,
            invariants=invariants_summary,
            consequences=consequence_summary,
            backstop=backstop.summary(),
        )

    def _apply_scenario_effects(
        self,
        scheduled: list[_ScheduledEffect],
        ctx: EffectContext,
        t_s: float,
        dt_s: float,
        events: EventBus,
    ) -> None:
        """Activate, tick and deactivate scenario effects for this timestep."""
        for item in scheduled:
            effect = resolve_effect(item.event.effect)
            end_t_s = item.event.end_t_s

            if not item.activated and t_s + 1e-9 >= item.event.t_s:
                effect.activate(ctx, item.params)
                item.activated = True
                events.emit(
                    Event(
                        t_s=t_s,
                        experiment_id=self._experiment_id,
                        source="scenario-engine",
                        zone=Zone.RANGE,
                        event_type=EventType.SCENARIO_EVENT,
                        asset_id=_effect_asset(item.event.effect),
                        severity=Severity.NOTICE,
                        data={
                            "phase": "activate",
                            "effect": item.event.effect,
                            "description": item.event.description,
                            "params": {
                                k: v
                                for k, v in sorted(item.params.items())
                                if not k.startswith("_")
                            },
                            "attack_ics": list(item.event.attack_ics),
                            "duration_s": item.event.duration_s,
                        },
                    )
                )

            if item.activated and not item.deactivated:
                if end_t_s is not None and t_s + 1e-9 >= end_t_s:
                    effect.deactivate(ctx, item.params)
                    item.deactivated = True
                    events.emit(
                        Event(
                            t_s=t_s,
                            experiment_id=self._experiment_id,
                            source="scenario-engine",
                            zone=Zone.RANGE,
                            event_type=EventType.SCENARIO_EVENT,
                            asset_id=_effect_asset(item.event.effect),
                            severity=Severity.NOTICE,
                            data={
                                "phase": "deactivate",
                                "effect": item.event.effect,
                                "description": item.event.description,
                            },
                        )
                    )
                else:
                    effect.tick(ctx, item.params, t_s - item.event.t_s, dt_s)


def _effect_asset(effect_name: str) -> str:
    """Map an effect to the asset it acts on, for the event envelope."""
    if effect_name.startswith("sensor."):
        return _ASSET_LEVEL_TX
    if effect_name.startswith("setpoint."):
        return _ASSET_CONTROLLER
    if effect_name.startswith("supervisory."):
        return "HMI-001"
    if effect_name.startswith("source."):
        return "RES-001"
    return _ASSET_TANK


def _invariant_severity(status: InvariantStatus) -> Severity:
    """Map invariant status to event severity."""
    match status:
        case InvariantStatus.VIOLATED:
            return Severity.CRITICAL
        case InvariantStatus.APPROACHING:
            return Severity.WARNING
        case _:
            return Severity.INFO


def _consequence_severity(level: ConsequenceLevel) -> Severity:
    """Map consequence class to event severity."""
    if level >= ConsequenceLevel.C4:
        return Severity.CRITICAL
    if level >= ConsequenceLevel.C2:
        return Severity.ERROR
    if level >= ConsequenceLevel.C1:
        return Severity.WARNING
    return Severity.INFO
