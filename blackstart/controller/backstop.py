"""Engineering backstop — a simulated independent engineering constraint.

This is the component the flagship experiment exists to measure. Its purpose is
narrow and specific:

    Prevent a digital compromise from directly producing an unacceptable
    physical state, without depending on the correctness of the control system,
    the operator, or the operator's instrumentation.

It sits logically downstream of every command path. A control request reaches an
actuator only through :meth:`EngineeringBackstop.evaluate`.

What "independent" means here, precisely
----------------------------------------
Three specific independences are modelled, and each is a claim that can be
checked against the code:

1. **Independent of the command path.** Policy thresholds are loaded from
   configuration at construction and are never writable at runtime. No scenario
   effect and no simulated command can reconfigure them.
2. **Independent of the operator's measurement.** The high-level trip reads the
   independent level element, which is modelled on a separate channel and is
   unaffected by ``sensor.*`` effects. *This is a modelling assumption.* A real
   independent element can itself be compromised; BLACKSTART does not claim
   otherwise, and ``docs/limitations.md`` says so.
3. **Independent of the invariant checker.** The backstop shares no code with
   :mod:`blackstart.core.invariants`. Neither imports the other. Without that
   separation, "backstop enabled implies no violations" would be a tautology
   rather than a measurement (ADR-004).

Backstop thresholds are deliberately tighter than the invariant limits they
protect, so the constraint acts *before* the safety limit is reached. The
configuration loader rejects any configuration where that is not true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blackstart.controller.control_logic import ControlRequest
from blackstart.core.config import BackstopConfig, ProcessConfig

__all__ = ["BackstopDecision", "EngineeringBackstop", "SetpointConstraint"]


@dataclass(frozen=True, slots=True)
class SetpointConstraint:
    """Outcome of the setpoint-constraint stage."""

    effective_setpoint_m: float
    #: Rules that modified the requested setpoint this scan.
    constrained_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BackstopDecision:
    """The command actually delivered to the actuators, and why."""

    effective_setpoint_m: float
    pump_permitted: bool
    valve_position: float
    #: Rules that modified the request this scan.
    constrained_by: tuple[str, ...] = ()
    #: Rules that denied the pump-run permissive this scan.
    denied_by: tuple[str, ...] = ()

    @property
    def acted(self) -> bool:
        """Whether the backstop altered the request in any way."""
        return bool(self.constrained_by or self.denied_by)


@dataclass(slots=True)
class _TripState:
    """Latched state of the independent high-level trip."""

    tripped: bool = False
    trip_count: int = 0
    first_trip_t_s: float | None = None


class EngineeringBackstop:
    """Independent command constraint and high-level pump trip.

    When ``enabled`` is false the backstop is a strict pass-through: it records
    nothing and changes nothing. That matters for the flagship comparison --
    the disabled variant must differ from the enabled variant in exactly one
    respect, the presence of this constraint.
    """

    def __init__(
        self,
        config: BackstopConfig,
        process: ProcessConfig,
        *,
        enabled: bool | None = None,
    ) -> None:
        """Bind the backstop to its policy and the process it protects.

        Args:
            config: Backstop policy from ``configs/architecture.yaml``.
            process: Process configuration, for the suction limit used by BS-04.
            enabled: Override the configured default. ``None`` uses the default.
        """
        self._config = config
        self._enabled = config.enabled_by_default if enabled is None else enabled

        # Policy thresholds are read once, here. They are never re-read and
        # never written, which is the first of the three independences above.
        clamp = config.rule("BS-01")
        self._setpoint_min_m = _required(clamp.setpoint_min_m, "BS-01.setpoint_min_m")
        self._setpoint_max_m = _required(clamp.setpoint_max_m, "BS-01.setpoint_max_m")

        slew = config.rule("BS-02")
        self._max_slew_m_s = _required(slew.max_slew_m_s, "BS-02.max_slew_m_s")

        trip = config.rule("BS-03")
        self._trip_level_m = _required(trip.trip_level_m, "BS-03.trip_level_m")
        self._reset_level_m = _required(trip.reset_level_m, "BS-03.reset_level_m")

        self._suction_limit_m = process.source.suction_limit_m
        self._min_off_time_s = _required(
            config.rule("BS-05").min_off_time_s, "BS-05.min_off_time_s"
        )

        self._trip = _TripState()
        self._effective_setpoint_m = process.control.operator_setpoint_m
        self._pump_permitted_last = False
        self._last_denied_t_s: float | None = None
        self._activations: dict[str, int] = {rule.id: 0 for rule in config.rules}

    @property
    def enabled(self) -> bool:
        """Whether the constraint is active for this experiment."""
        return self._enabled

    @property
    def activation_counts(self) -> dict[str, int]:
        """Per-rule activation counts, recorded in the evidence package.

        Reported honestly: a rule that never acted in a given experiment shows
        zero. BS-05 is redundant with the controller's own anti-cycling under the
        shipped scenarios and is expected to read zero there.
        """
        return dict(self._activations)

    @property
    def trip_state(self) -> dict[str, Any]:
        """Summary of independent high-level trip activity."""
        return {
            "currently_tripped": self._trip.tripped,
            "trip_count": self._trip.trip_count,
            "first_trip_t_s": self._trip.first_trip_t_s,
        }

    def constrain_setpoint(self, requested_setpoint_m: float, dt_s: float) -> SetpointConstraint:
        """Stage one: constrain the setpoint before any control request is formed.

        This runs *upstream* of the controller, not alongside it. The controller
        never sees the requested setpoint and never pursues it, so an
        out-of-range target cannot become a control action in the first place.
        Applying the clamp downstream of the control request would leave the
        controller chasing an unsafe target and rely entirely on the pump trip to
        catch the result -- defence by a single layer rather than two.

        Args:
            requested_setpoint_m: The setpoint held by the supervisory layer,
                whatever its origin.
            dt_s: Timestep length in seconds, for the slew limit.

        Returns:
            The setpoint the controller will actually act on.
        """
        if not self._enabled:
            # Strict pass-through. The disabled variant must be the control case.
            self._effective_setpoint_m = requested_setpoint_m
            return SetpointConstraint(effective_setpoint_m=requested_setpoint_m)

        constrained: list[str] = []

        # BS-01 -- absolute clamp, applied regardless of command origin or
        # claimed authorisation.
        clamped = min(self._setpoint_max_m, max(self._setpoint_min_m, requested_setpoint_m))
        if clamped != requested_setpoint_m:
            constrained.append("BS-01")
            self._activations["BS-01"] += 1

        # BS-02 -- slew limit, so a single mutated command cannot step the
        # process target even within the permitted range.
        delta = clamped - self._effective_setpoint_m
        max_travel = self._max_slew_m_s * dt_s
        if abs(delta) > max_travel:
            effective = self._effective_setpoint_m + (max_travel if delta > 0 else -max_travel)
            constrained.append("BS-02")
            self._activations["BS-02"] += 1
        else:
            effective = clamped
        self._effective_setpoint_m = effective

        return SetpointConstraint(effective_setpoint_m=effective, constrained_by=tuple(constrained))

    def evaluate_permissive(
        self,
        request: ControlRequest,
        constraint: SetpointConstraint,
        *,
        independent_level_m: float,
        source_level_m: float,
        t_s: float,
    ) -> BackstopDecision:
        """Stage two: apply the actuator interlocks to a formed control request.

        Args:
            request: The control action the controller wishes to take.
            constraint: The stage-one setpoint outcome, carried through so the
                decision records both stages.
            independent_level_m: Reading from the independent level element.
            source_level_m: True source reservoir level, for the suction interlock.
            t_s: Current simulation time in seconds.

        Returns:
            The command that will actually be delivered to the actuators.
        """
        if not self._enabled:
            return BackstopDecision(
                effective_setpoint_m=constraint.effective_setpoint_m,
                pump_permitted=request.pump_run,
                valve_position=request.valve_position,
            )

        denied: list[str] = []

        # BS-03 -- independent high-level trip. Latched, with hysteresis, and
        # driven by the independent element rather than the operator transmitter.
        # This is the rule that survives falsification of the level transmitter.
        if self._trip.tripped:
            if independent_level_m <= self._reset_level_m:
                self._trip.tripped = False
        elif independent_level_m >= self._trip_level_m:
            self._trip.tripped = True
            self._trip.trip_count += 1
            if self._trip.first_trip_t_s is None:
                self._trip.first_trip_t_s = t_s

        pump_permitted = request.pump_run
        if self._trip.tripped and pump_permitted:
            pump_permitted = False
            denied.append("BS-03")
            self._activations["BS-03"] += 1

        # BS-04 -- dry-run suction interlock.
        if pump_permitted and source_level_m <= self._suction_limit_m:
            pump_permitted = False
            denied.append("BS-04")
            self._activations["BS-04"] += 1

        # BS-05 -- anti-cycle minimum off time, bounding motor start frequency
        # independently of the controller's own timer.
        is_start = pump_permitted and not self._pump_permitted_last
        if (
            is_start
            and self._last_denied_t_s is not None
            and (t_s - self._last_denied_t_s) < self._min_off_time_s
        ):
            pump_permitted = False
            denied.append("BS-05")
            self._activations["BS-05"] += 1

        if self._pump_permitted_last and not pump_permitted:
            self._last_denied_t_s = t_s
        self._pump_permitted_last = pump_permitted

        return BackstopDecision(
            effective_setpoint_m=constraint.effective_setpoint_m,
            pump_permitted=pump_permitted,
            valve_position=request.valve_position,
            constrained_by=constraint.constrained_by,
            denied_by=tuple(denied),
        )

    def summary(self) -> dict[str, Any]:
        """Backstop activity summary for the evidence package."""
        return {
            "backstop_id": self._config.id,
            "enabled": self._enabled,
            "activation_counts": self.activation_counts,
            "trip": self.trip_state,
            "thresholds": {
                "setpoint_min_m": self._setpoint_min_m,
                "setpoint_max_m": self._setpoint_max_m,
                "max_slew_m_s": self._max_slew_m_s,
                "trip_level_m": self._trip_level_m,
                "reset_level_m": self._reset_level_m,
                "min_off_time_s": self._min_off_time_s,
            },
        }


def _required(value: float | None, name: str) -> float:
    """Return a required backstop threshold or fail loudly.

    Raises:
        ValueError: if the threshold is not configured. A safety constraint must
            never silently default.
    """
    if value is None:
        msg = f"engineering backstop requires {name} to be configured"
        raise ValueError(msg)
    return value
