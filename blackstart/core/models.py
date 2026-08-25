"""Simulation state models.

Two separate representations of the process are maintained at all times:

``TruthState``
    What is physically happening. Only the physics integrator writes it. This is
    what invariants evaluate and what the evidence package records.

``ReportedState``
    What the control system and the operator believe is happening. Produced by
    the sensor model and mutable by ``sensor.*`` scenario effects.

Keeping these apart is the single most load-bearing modelling decision in
BLACKSTART. It is why a scenario that deceives the operator cannot also falsify
the experimental record, and why "the process was damaged" and "the operator was
deceived" are independently measurable outcomes (ADR-002, ADR-004).

Per-timestep state uses mutable dataclasses rather than Pydantic models: the
integration loop rewrites them thousands of times per run, and validation belongs
at the configuration boundary, not in the hot path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "CommandState",
    "ConsequenceLevel",
    "InvariantStatus",
    "ProcessState",
    "ReportedState",
    "TruthState",
]


class InvariantStatus(StrEnum):
    """Three-valued invariant outcome.

    ``APPROACHING`` is the leading indicator: the process is within the
    invariant's configured margin of its limit but has not breached it. It is
    what lets BLACKSTART measure how much warning an engineered control bought,
    rather than only whether a limit was crossed (ADR-004).
    """

    OK = "OK"
    APPROACHING = "APPROACHING"
    VIOLATED = "VIOLATED"


class ConsequenceLevel(StrEnum):
    """Ordered consequence severity classes.

    Ordering is defined by :attr:`rank`, not by the string value, so severity
    comparisons remain correct and explicit.
    """

    C0 = "C0"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"

    @property
    def rank(self) -> int:
        """Integer severity rank, 0 (normal) through 5 (catastrophic)."""
        return int(self.value[1])

    def __lt__(self, other: object) -> bool:
        """Compare severity by rank."""
        if not isinstance(other, ConsequenceLevel):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        """Compare severity by rank."""
        if not isinstance(other, ConsequenceLevel):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        """Compare severity by rank."""
        if not isinstance(other, ConsequenceLevel):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        """Compare severity by rank."""
        if not isinstance(other, ConsequenceLevel):
            return NotImplemented
        return self.rank >= other.rank


@dataclass(slots=True)
class TruthState:
    """Ground-truth physical state of the process.

    Written only by :class:`blackstart.core.physics.process.WaterProcessModel`.
    No scenario effect writes here except through a declared physical input
    (demand and source level), because an adversary manipulating a control system
    changes what the process is *told to do*, not what physics does.
    """

    tank_level_m: float
    source_level_m: float
    #: The pump motor is energised. Note this is distinct from delivering flow:
    #: during a dry-run condition the motor is energised and inflow is zero,
    #: which is precisely the damaging state INV-003 detects.
    pump_energised: bool
    valve_position: float
    inflow_m3_s: float = 0.0
    outflow_m3_s: float = 0.0
    demand_m3_s: float = 0.0
    #: Cumulative volume discharged through the overflow weir.
    spill_volume_m3: float = 0.0
    spill_rate_m3_s: float = 0.0

    @property
    def has_suction(self) -> bool:
        """Whether the pump is delivering flow rather than running dry."""
        return self.inflow_m3_s > 0.0

    @property
    def service_shortfall_m3_s(self) -> float:
        """Demand that the hydraulics failed to deliver, in m3/s."""
        return max(0.0, self.demand_m3_s - self.outflow_m3_s)

    @property
    def service_shortfall_ratio(self) -> float:
        """Undelivered fraction of demand, in ``[0, 1]``."""
        if self.demand_m3_s <= 0.0:
            return 0.0
        return self.service_shortfall_m3_s / self.demand_m3_s


@dataclass(slots=True)
class ReportedState:
    """Process state as reported by instrumentation to the control system.

    This is what the controller acts on and what the HMI displays. Scenario
    effects in the ``sensor.*`` family mutate this and nothing else.
    """

    tank_level_m: float
    inflow_m3_s: float
    outflow_m3_s: float
    pump_energised: bool
    valve_position: float
    #: False while a ``supervisory.blackout`` effect is active. The controller
    #: continues to run on local instrumentation; only the supervisory view is
    #: lost, which is the distinction SCN-005 exists to make.
    supervisory_available: bool = True


@dataclass(slots=True)
class CommandState:
    """Control intent, and the record of what the backstop did to it."""

    #: Setpoint as held by the supervisory layer. A ``setpoint.override`` effect
    #: writes here, standing in for an unauthorised control-state change.
    requested_setpoint_m: float
    #: Setpoint after the engineering backstop has applied its policy. When the
    #: backstop is disabled this equals ``requested_setpoint_m``.
    effective_setpoint_m: float
    pump_permissive: bool = True
    pump_command: bool = False
    valve_command: float = 1.0
    pump_starts: int = 0
    #: Identifiers of backstop rules that modified or denied this scan's command.
    backstop_actions: list[str] = field(default_factory=list)

    @property
    def setpoint_was_constrained(self) -> bool:
        """Whether the backstop altered the requested setpoint this scan."""
        return self.effective_setpoint_m != self.requested_setpoint_m


@dataclass(slots=True)
class ProcessState:
    """Complete simulation state at one timestep."""

    t_s: float
    truth: TruthState
    reported: ReportedState
    command: CommandState
    #: Reading from the independent level element, used only by the backstop.
    independent_level_m: float

    @property
    def telemetry_divergence_m(self) -> float:
        """Absolute difference between reported and true tank level."""
        return abs(self.reported.tank_level_m - self.truth.tank_level_m)
