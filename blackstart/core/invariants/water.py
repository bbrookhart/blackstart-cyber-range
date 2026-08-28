"""Concrete safety and mission invariants for the water storage process.

Each class implements one entry in ``configs/invariants.yaml``. All of them read
:class:`~blackstart.core.models.TruthState` -- what physically happened -- with
the single deliberate exception of :class:`TelemetryIntegrityInvariant`, whose
purpose is to compare truth against the reported view.

That asymmetry is the reason a scenario effect which deceives the operator cannot
also falsify the experimental record (ADR-004).
"""

from __future__ import annotations

from blackstart.core.config import InvariantSpec, ProcessConfig
from blackstart.core.invariants.base import Invariant, Observation
from blackstart.core.models import ProcessState

__all__ = [
    "CommandRateInvariant",
    "DryRunInvariant",
    "MaximumLevelInvariant",
    "MinimumReserveInvariant",
    "SetpointBoundInvariant",
    "TelemetryIntegrityInvariant",
]

# Rate estimation needs a minimum observation window, or the first pump start in
# a run would imply an unbounded starts-per-hour figure.
_MIN_RATE_WINDOW_S = 600.0
_RATE_WINDOW_S = 3600.0


def _require(value: float | None, spec_id: str, field_name: str) -> float:
    """Return a required numeric field or fail loudly.

    Missing configuration for a safety limit must never default silently.

    Raises:
        ValueError: if the field is absent from the specification.
    """
    if value is None:
        msg = f"{spec_id} requires '{field_name}' to be configured"
        raise ValueError(msg)
    return value


class MaximumLevelInvariant(Invariant):
    """INV-001 — the true tank level must not exceed the safe working level.

    Instantaneous: there is no tolerance period for exceeding a structural safe
    level. The limit sits below the physical overflow height, so a violation is
    an observable, recoverable excursion rather than immediate loss of
    containment.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind to the INV-001 specification."""
        super().__init__(spec)
        self._limit_m = _require(spec.limit_m, spec.id, "limit_m")
        self._margin_m = _require(spec.margin_m, spec.id, "margin_m")

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe the true tank level against the safe maximum."""
        del dt_s
        level = state.truth.tank_level_m
        return Observation(
            value=level,
            breaching=level > self._limit_m,
            approaching=level >= self._limit_m - self._margin_m,
            detail={"spill_volume_m3": state.truth.spill_volume_m3},
        )


class MinimumReserveInvariant(Invariant):
    """INV-002 — the operational reserve must not be lost beyond its tolerance.

    Temporal: brief excursions below the reserve during a demand surge are
    operationally normal. A sustained excursion is a loss of the required
    service, which is why this invariant maps to consequence class C3.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind to the INV-002 specification."""
        super().__init__(spec)
        self._limit_m = _require(spec.limit_m, spec.id, "limit_m")
        self._margin_m = _require(spec.margin_m, spec.id, "margin_m")

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe the true tank level against the minimum reserve."""
        del dt_s
        level = state.truth.tank_level_m
        return Observation(
            value=level,
            breaching=level < self._limit_m,
            approaching=level <= self._limit_m + self._margin_m,
        )


class DryRunInvariant(Invariant):
    """INV-003 — the pump must not remain energised without suction.

    Conditional. This condition is invisible in a level trend alone: the motor
    draws current and the control system believes it is pumping, while the tank
    simply does not fill. The short tolerance allows one control scan for the
    interlock to act before the condition counts as a violation.
    """

    def __init__(self, spec: InvariantSpec, process: ProcessConfig) -> None:
        """Bind to the INV-003 specification and the process suction limit."""
        super().__init__(spec)
        self._suction_limit_m = process.source.suction_limit_m
        self._margin_m = _require(spec.margin_m, spec.id, "margin_m")

    @property
    def limit(self) -> float | None:
        """The suction limit, in metres of source level."""
        return self._suction_limit_m

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe pump energisation against available suction."""
        del dt_s
        energised = state.truth.pump_energised
        source_level = state.truth.source_level_m
        return Observation(
            value=source_level,
            breaching=energised and source_level <= self._suction_limit_m,
            approaching=energised and source_level <= self._suction_limit_m + self._margin_m,
            detail={
                "pump_energised": float(energised),
                "inflow_m3_s": state.truth.inflow_m3_s,
            },
        )


class CommandRateInvariant(Invariant):
    """INV-004 — control commands must be physically achievable and equipment-safe.

    Two conditions, either of which breaches: setpoint slew rate, and pump motor
    start frequency.

    This invariant observes the **requested** setpoint, not the effective one.
    The question it asks is "was a physically implausible command issued?", and
    the answer does not change because a downstream constraint later refused it.
    Observing the effective setpoint would make the signal disappear precisely
    when the engineering backstop is doing its job -- destroying a
    variant-independent detection opportunity. See ADR-004.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind to the INV-004 specification."""
        super().__init__(spec)
        self._max_slew_m_s = _require(spec.max_setpoint_slew_m_s, spec.id, "max_setpoint_slew_m_s")
        self._max_starts_per_hour = _require(
            spec.max_pump_starts_per_hour, spec.id, "max_pump_starts_per_hour"
        )
        self._previous_setpoint_m: float | None = None
        self._previous_start_count = 0
        self._start_times_s: list[float] = []

    @property
    def limit(self) -> float | None:
        """The pump start-rate limit, in starts per hour."""
        return self._max_starts_per_hour

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe setpoint slew rate and pump start frequency."""
        requested = state.command.requested_setpoint_m

        if self._previous_setpoint_m is None:
            slew_m_s = 0.0
        else:
            slew_m_s = abs(requested - self._previous_setpoint_m) / dt_s
        self._previous_setpoint_m = requested

        if state.command.pump_starts > self._previous_start_count:
            self._start_times_s.append(state.t_s)
        self._previous_start_count = state.command.pump_starts
        self._start_times_s = [t for t in self._start_times_s if state.t_s - t <= _RATE_WINDOW_S]

        window_s = max(_MIN_RATE_WINDOW_S, min(state.t_s, _RATE_WINDOW_S))
        starts_per_hour = len(self._start_times_s) * (3600.0 / window_s)

        slew_breach = slew_m_s > self._max_slew_m_s
        rate_breach = starts_per_hour > self._max_starts_per_hour

        return Observation(
            value=starts_per_hour,
            breaching=slew_breach or rate_breach,
            approaching=starts_per_hour > 0.8 * self._max_starts_per_hour,
            detail={
                "setpoint_slew_m_s": slew_m_s,
                "starts_per_hour": starts_per_hour,
                "slew_breach": float(slew_breach),
                "rate_breach": float(rate_breach),
            },
        )


class SetpointBoundInvariant(Invariant):
    """INV-005 — the effective control target must remain physically acceptable.

    Unlike INV-004, which preserves evidence of the adversary's requested
    mutation, this invariant observes the value that actually reaches the
    controller. It is therefore the executable form of the flagship assurance
    property: with the backstop active, an unsafe request may still exist in
    evidence but cannot become an unsafe effective target.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind the configured minimum and maximum effective setpoints."""
        super().__init__(spec)
        self._minimum_m = _require(
            spec.min_effective_setpoint_m, spec.id, "min_effective_setpoint_m"
        )
        self._maximum_m = _require(
            spec.max_effective_setpoint_m, spec.id, "max_effective_setpoint_m"
        )
        if self._minimum_m >= self._maximum_m:
            msg = f"{spec.id} requires min_effective_setpoint_m < max_effective_setpoint_m"
            raise ValueError(msg)

    @property
    def limit(self) -> float | None:
        """Upper engineering limit, used for evidence display."""
        return self._maximum_m

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe the effective target after any independent constraint."""
        del dt_s
        effective = state.command.effective_setpoint_m
        below = effective < self._minimum_m
        above = effective > self._maximum_m
        return Observation(
            value=effective,
            breaching=below or above,
            detail={
                "requested_setpoint_m": state.command.requested_setpoint_m,
                "effective_setpoint_m": effective,
                "minimum_m": self._minimum_m,
                "maximum_m": self._maximum_m,
            },
        )


class TelemetryIntegrityInvariant(Invariant):
    """INV-006 — reported process state must track true process state.

    The only invariant permitted to read both views. It makes loss of telemetry
    integrity a measured condition rather than an untracked assumption, and it
    remains correct even while the operator-facing view is wrong.

    A violation here is not itself a physical consequence, which is why it maps
    to C1: the process may still be perfectly safe while the operator's
    understanding of it is not.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind to the INV-005 specification."""
        super().__init__(spec)
        self._max_divergence_m = _require(spec.max_divergence_m, spec.id, "max_divergence_m")
        self._margin_m = _require(spec.margin_m, spec.id, "margin_m")

    @property
    def limit(self) -> float | None:
        """Maximum tolerated divergence between reported and true level."""
        return self._max_divergence_m

    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Observe the divergence between reported and true tank level."""
        del dt_s
        divergence = state.telemetry_divergence_m
        return Observation(
            value=divergence,
            breaching=divergence > self._max_divergence_m,
            approaching=divergence >= self._max_divergence_m - self._margin_m,
            detail={
                "reported_level_m": state.reported.tank_level_m,
                "true_level_m": state.truth.tank_level_m,
            },
        )
