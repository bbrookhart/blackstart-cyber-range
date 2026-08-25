"""Invariant abstractions and temporal bookkeeping.

An invariant in BLACKSTART is a *stateful temporal predicate*, not a stateless
assertion. Real OT safety conditions almost never are instantaneous: "the tank is
below reserve" is not a violation, "the tank has been below reserve for longer
than the tolerance" is. Putting that accumulation in the invariant rather than in
the metrics layer keeps safety-relevant logic where it is tested as safety logic
(ADR-004).

Subclasses implement :meth:`Invariant.observe` and return only the raw
observation. All duration accumulation, interval tracking, peak-excursion
recording and three-valued status derivation live in :class:`Invariant` so that
every invariant behaves identically in those respects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from blackstart.core.config import InvariantSpec
from blackstart.core.models import InvariantStatus, ProcessState

__all__ = [
    "Invariant",
    "InvariantOutcome",
    "InvariantSample",
    "Observation",
    "ViolationInterval",
]


@dataclass(frozen=True, slots=True)
class Observation:
    """Raw per-step observation returned by a concrete invariant.

    Attributes:
        value: The observed quantity, in the invariant's natural units.
        breaching: Whether the underlying predicate is breached *right now*,
            before any tolerance period is applied.
        approaching: Whether the observation is within the configured margin of
            the limit but not breaching.
        detail: Optional additional observed quantities recorded in evidence.
    """

    value: float
    breaching: bool
    approaching: bool = False
    detail: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InvariantSample:
    """One invariant's evaluated status at one timestep."""

    invariant_id: str
    t_s: float
    status: InvariantStatus
    value: float
    limit: float | None
    detail: dict[str, float] = field(default_factory=dict)

    @property
    def violated(self) -> bool:
        """Whether this sample records a violation."""
        return self.status is InvariantStatus.VIOLATED


@dataclass(slots=True)
class ViolationInterval:
    """A contiguous period during which an invariant was violated."""

    start_s: float
    end_s: float | None = None
    peak_value: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the evidence package."""
        return {
            "start_s": round(self.start_s, 3),
            "end_s": None if self.end_s is None else round(self.end_s, 3),
            "duration_s": None if self.end_s is None else round(self.end_s - self.start_s, 3),
            "peak_value": round(self.peak_value, 6),
        }


@dataclass(slots=True)
class InvariantOutcome:
    """Aggregate result for one invariant across a whole experiment."""

    invariant_id: str
    name: str
    severity_on_violation: str
    limit: float | None
    violated: bool
    violation_count: int
    total_violation_s: float
    total_approaching_s: float
    peak_excursion: float
    first_violation_t_s: float | None
    intervals: list[ViolationInterval]

    def as_dict(self) -> dict[str, Any]:
        """Serialise for ``invariants.json`` in the evidence package."""
        return {
            "invariant_id": self.invariant_id,
            "name": self.name,
            "severity_on_violation": self.severity_on_violation,
            "limit": self.limit,
            "violated": self.violated,
            "violation_count": self.violation_count,
            "total_violation_s": round(self.total_violation_s, 3),
            "total_approaching_s": round(self.total_approaching_s, 3),
            "peak_excursion": round(self.peak_excursion, 6),
            "first_violation_t_s": None
            if self.first_violation_t_s is None
            else round(self.first_violation_t_s, 3),
            "intervals": [interval.as_dict() for interval in self.intervals],
        }


class Invariant(ABC):
    """Base class for BLACKSTART safety and mission invariants.

    A fresh instance is constructed per experiment. Instances carry accumulated
    temporal state and must never be shared between runs; the runner enforces
    this and an integration test asserts it.
    """

    def __init__(self, spec: InvariantSpec) -> None:
        """Bind the invariant to its declarative specification."""
        self._spec = spec
        self._breach_duration_s = 0.0
        self._total_violation_s = 0.0
        self._total_approaching_s = 0.0
        self._peak_excursion = 0.0
        self._first_violation_t_s: float | None = None
        self._intervals: list[ViolationInterval] = []
        self._open_interval: ViolationInterval | None = None

    @property
    def spec(self) -> InvariantSpec:
        """The declarative specification backing this invariant."""
        return self._spec

    @property
    def invariant_id(self) -> str:
        """Identifier such as ``INV-001``."""
        return self._spec.id

    @property
    def limit(self) -> float | None:
        """The primary numeric limit, where the invariant has one."""
        return self._spec.limit_m

    @abstractmethod
    def observe(self, state: ProcessState, dt_s: float) -> Observation:
        """Return the raw observation for this timestep.

        Implementations must not accumulate duration or mutate ``state``.
        """

    def _excursion(self, value: float) -> float:
        """Magnitude of the breach, for peak-excursion reporting."""
        if self.limit is None:
            return abs(value)
        return abs(value - self.limit)

    def evaluate(self, state: ProcessState, dt_s: float) -> InvariantSample:
        """Evaluate the invariant for one timestep and update its history.

        Args:
            state: Complete simulation state at this timestep.
            dt_s: Timestep length in seconds.

        Returns:
            The evaluated sample, including three-valued status.
        """
        observation = self.observe(state, dt_s)

        if observation.breaching:
            self._breach_duration_s += dt_s
        else:
            self._breach_duration_s = 0.0

        # A breach becomes a violation only once it has persisted for at least
        # the configured tolerance. With tolerance 0 the first breaching step
        # violates immediately.
        is_violation = observation.breaching and self._breach_duration_s >= self._spec.tolerance_s

        if is_violation:
            status = InvariantStatus.VIOLATED
            self._total_violation_s += dt_s
            excursion = self._excursion(observation.value)
            self._peak_excursion = max(self._peak_excursion, excursion)
            if self._open_interval is None:
                self._open_interval = ViolationInterval(
                    start_s=state.t_s, peak_value=observation.value
                )
                self._intervals.append(self._open_interval)
                if self._first_violation_t_s is None:
                    self._first_violation_t_s = state.t_s
            else:
                self._open_interval.peak_value = (
                    max(self._open_interval.peak_value, observation.value)
                    if self._peak_is_upward
                    else min(self._open_interval.peak_value, observation.value)
                )
        else:
            if self._open_interval is not None:
                self._open_interval.end_s = state.t_s
                self._open_interval = None
            if observation.breaching or observation.approaching:
                # Breaching-but-within-tolerance is the leading indicator too.
                status = InvariantStatus.APPROACHING
                self._total_approaching_s += dt_s
            else:
                status = InvariantStatus.OK

        return InvariantSample(
            invariant_id=self._spec.id,
            t_s=state.t_s,
            status=status,
            value=observation.value,
            limit=self.limit,
            detail=observation.detail,
        )

    @property
    def _peak_is_upward(self) -> bool:
        """Whether a worse violation means a larger observed value."""
        return self._spec.kind != "temporal_lower_bound"

    def finalise(self, final_t_s: float) -> InvariantOutcome:
        """Close any open violation interval and return the aggregate outcome."""
        if self._open_interval is not None:
            self._open_interval.end_s = final_t_s
            self._open_interval = None
        return InvariantOutcome(
            invariant_id=self._spec.id,
            name=self._spec.name,
            severity_on_violation=self._spec.severity_on_violation,
            limit=self.limit,
            violated=bool(self._intervals),
            violation_count=len(self._intervals),
            total_violation_s=self._total_violation_s,
            total_approaching_s=self._total_approaching_s,
            peak_excursion=self._peak_excursion,
            first_violation_t_s=self._first_violation_t_s,
            intervals=list(self._intervals),
        )
