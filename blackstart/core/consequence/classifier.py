"""Consequence classification.

Consequence severity is *derived* each timestep from measurable process
conditions and invariant status. Nothing in BLACKSTART assigns a consequence
class directly -- not a scenario, not an effect, not an operator. That is what
makes a reported "maximum consequence C4" a result rather than a label.

The classifier is explicit typed code rather than an interpreter over the
condition tree in ``configs/consequences.yaml``. Safety classification should be
readable in one place and directly unit-testable; a rule engine would move the
logic into data where it is much harder to reason about. The configuration
remains the authority for the *thresholds*, and
``tests/unit/test_consequence_config_alignment.py`` asserts that the code and the
configured condition tree have not drifted apart.

Escalation is deliberately hard. C4 requires a violated physical-safety invariant
(INV-001 or INV-003). C5 requires loss of containment at scale, or a prolonged
unsafe state coincident with loss of the required service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from blackstart.core.config import ConsequencesConfig
from blackstart.core.invariants.engine import InvariantStepResult
from blackstart.core.models import ConsequenceLevel, ProcessState

__all__ = ["ConsequenceClassifier", "ConsequenceSample", "ConsequenceSummary"]

# Invariants whose violation constitutes an unsafe physical state (C4).
_UNSAFE_PHYSICAL_INVARIANTS = frozenset({"INV-001", "INV-003"})
# Invariants whose violation is operationally noteworthy but not a physical
# consequence in itself (C1).
_ADVISORY_INVARIANTS = frozenset({"INV-004", "INV-005", "INV-006"})
# Invariant whose violation is by definition a loss of the required service (C3).
_SERVICE_LOSS_INVARIANTS = frozenset({"INV-002"})


@dataclass(frozen=True, slots=True)
class ConsequenceSample:
    """Consequence classification at one timestep."""

    t_s: float
    level: ConsequenceLevel
    #: Human-readable reasons this class was reached, for the evidence record.
    drivers: tuple[str, ...]
    service_shortfall_ratio: float
    level_in_normal_band: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the evidence package."""
        return {
            "t_s": round(self.t_s, 3),
            "level": self.level.value,
            "drivers": list(self.drivers),
            "service_shortfall_ratio": round(self.service_shortfall_ratio, 6),
            "level_in_normal_band": self.level_in_normal_band,
        }


@dataclass(slots=True)
class ConsequenceSummary:
    """Aggregate consequence outcome for a whole experiment."""

    maximum_level: ConsequenceLevel
    time_at_level_s: dict[str, float]
    transitions: list[dict[str, Any]] = field(default_factory=list)
    first_reached_t_s: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise for ``consequences.json`` in the evidence package."""
        return {
            "maximum_level": self.maximum_level.value,
            "time_at_level_s": {k: round(v, 3) for k, v in sorted(self.time_at_level_s.items())},
            "first_reached_t_s": {
                k: round(v, 3) for k, v in sorted(self.first_reached_t_s.items())
            },
            "transitions": self.transitions,
        }


class ConsequenceClassifier:
    """Derives consequence severity from process state and invariant status.

    Carries the sustained-condition timers that distinguish a transient dip from
    a genuine service consequence. A fresh instance is required per experiment.
    """

    def __init__(self, config: ConsequencesConfig) -> None:
        """Bind the classifier to the consequence taxonomy configuration."""
        self._config = config
        self._degradation_duration_s = 0.0
        self._loss_duration_s = 0.0
        self._time_in_c4_s = 0.0
        self._time_at_level_s: dict[str, float] = {level.value: 0.0 for level in ConsequenceLevel}
        self._first_reached_t_s: dict[str, float] = {}
        self._transitions: list[dict[str, Any]] = []
        self._previous_level: ConsequenceLevel | None = None
        self._maximum_level = ConsequenceLevel.C0

    @property
    def maximum_level(self) -> ConsequenceLevel:
        """Highest consequence class reached so far."""
        return self._maximum_level

    def classify(
        self, state: ProcessState, invariants: InvariantStepResult, dt_s: float
    ) -> ConsequenceSample:
        """Classify the consequence state for one timestep.

        Args:
            state: Complete simulation state.
            invariants: Invariant evaluation for the same timestep.
            dt_s: Timestep length in seconds.

        Returns:
            The classified sample, with the reasons the class was reached.
        """
        cfg = self._config
        violated = invariants.violated_ids
        shortfall = state.truth.service_shortfall_ratio
        level_m = state.truth.tank_level_m
        in_band = cfg.normal_band.lower_m <= level_m <= cfg.normal_band.upper_m

        # Sustained-condition timers. These reset on recovery, so a class is
        # only reached by a genuinely continuous condition.
        self._degradation_duration_s = (
            self._degradation_duration_s + dt_s
            if shortfall >= cfg.degradation_shortfall_ratio
            else 0.0
        )
        self._loss_duration_s = (
            self._loss_duration_s + dt_s if shortfall >= cfg.loss_shortfall_ratio else 0.0
        )

        drivers: list[str] = []
        level = ConsequenceLevel.C0

        # C1 -- minor operational deviation.
        if not in_band:
            level = ConsequenceLevel.C1
            drivers.append(
                f"tank level {level_m:.3f} m outside normal band "
                f"[{cfg.normal_band.lower_m:.2f}, {cfg.normal_band.upper_m:.2f}] m"
            )
        if shortfall >= cfg.minor_shortfall_ratio:
            level = max(level, ConsequenceLevel.C1)
            drivers.append(f"service shortfall {shortfall:.1%}")
        advisory = violated & _ADVISORY_INVARIANTS
        if advisory:
            level = max(level, ConsequenceLevel.C1)
            drivers.append(f"advisory invariant violated: {', '.join(sorted(advisory))}")

        # C2 -- sustained service degradation.
        if self._degradation_duration_s >= cfg.degradation_sustained_s:
            level = max(level, ConsequenceLevel.C2)
            drivers.append(
                f"shortfall >= {cfg.degradation_shortfall_ratio:.0%} sustained "
                f"{self._degradation_duration_s:.0f} s"
            )

        # C3 -- loss of required service.
        if self._loss_duration_s >= cfg.loss_sustained_s:
            level = max(level, ConsequenceLevel.C3)
            drivers.append(
                f"shortfall >= {cfg.loss_shortfall_ratio:.0%} sustained "
                f"{self._loss_duration_s:.0f} s"
            )
        service_loss = violated & _SERVICE_LOSS_INVARIANTS
        if service_loss:
            level = max(level, ConsequenceLevel.C3)
            drivers.append(f"operational reserve lost: {', '.join(sorted(service_loss))}")

        # C4 -- unsafe physical state.
        unsafe = violated & _UNSAFE_PHYSICAL_INVARIANTS
        if unsafe:
            level = max(level, ConsequenceLevel.C4)
            drivers.append(f"physical safety invariant violated: {', '.join(sorted(unsafe))}")

        if level >= ConsequenceLevel.C4:
            self._time_in_c4_s += dt_s

        # C5 -- catastrophic. Requires containment loss at scale, or a prolonged
        # unsafe state that is *also* a loss of the required service.
        spill = state.truth.spill_volume_m3
        if spill >= cfg.catastrophic_spill_m3:
            level = ConsequenceLevel.C5
            drivers.append(f"containment loss {spill:.1f} m3 through overflow weir")
        elif (
            self._time_in_c4_s >= cfg.catastrophic_unsafe_s
            and level >= ConsequenceLevel.C4
            and (bool(service_loss) or self._loss_duration_s >= cfg.loss_sustained_s)
        ):
            level = ConsequenceLevel.C5
            drivers.append(
                f"unsafe state sustained {self._time_in_c4_s:.0f} s coincident with "
                f"loss of required service"
            )

        self._record(state.t_s, level, dt_s)
        return ConsequenceSample(
            t_s=state.t_s,
            level=level,
            drivers=tuple(drivers),
            service_shortfall_ratio=shortfall,
            level_in_normal_band=in_band,
        )

    def _record(self, t_s: float, level: ConsequenceLevel, dt_s: float) -> None:
        """Update aggregate bookkeeping for this timestep."""
        self._time_at_level_s[level.value] += dt_s
        if level > self._maximum_level:
            self._maximum_level = level
        if level.value not in self._first_reached_t_s:
            self._first_reached_t_s[level.value] = t_s
        if self._previous_level is not None and level is not self._previous_level:
            self._transitions.append(
                {
                    "t_s": round(t_s, 3),
                    "from": self._previous_level.value,
                    "to": level.value,
                }
            )
        self._previous_level = level

    def summary(self) -> ConsequenceSummary:
        """Build the aggregate consequence outcome for the evidence package."""
        return ConsequenceSummary(
            maximum_level=self._maximum_level,
            time_at_level_s=dict(self._time_at_level_s),
            transitions=list(self._transitions),
            first_reached_t_s=dict(self._first_reached_t_s),
        )
