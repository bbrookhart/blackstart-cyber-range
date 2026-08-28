"""Invariant engine: constructs, evaluates and aggregates the invariant set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blackstart.core.config import InvariantsConfig, InvariantSpec, ProcessConfig
from blackstart.core.invariants.base import Invariant, InvariantOutcome, InvariantSample
from blackstart.core.invariants.water import (
    CommandRateInvariant,
    DryRunInvariant,
    MaximumLevelInvariant,
    MinimumReserveInvariant,
    SetpointBoundInvariant,
    TelemetryIntegrityInvariant,
)
from blackstart.core.models import InvariantStatus, ProcessState

__all__ = ["InvariantEngine", "InvariantStepResult", "build_invariants"]


def build_invariants(
    invariants_config: InvariantsConfig, process: ProcessConfig
) -> list[Invariant]:
    """Instantiate the configured invariants in declaration order.

    The mapping from identifier to implementation is explicit rather than
    dynamic. Safety logic should not be resolved by string lookup into whatever
    happens to be importable.

    Raises:
        ValueError: if the configuration names an invariant with no implementation.
    """
    built: list[Invariant] = []
    for spec in invariants_config.invariants:
        built.append(_build_one(spec, process))
    return built


def _build_one(spec: InvariantSpec, process: ProcessConfig) -> Invariant:
    """Instantiate a single invariant from its specification.

    Raises:
        ValueError: if ``spec.id`` has no corresponding implementation.
    """
    match spec.id:
        case "INV-001":
            return MaximumLevelInvariant(spec)
        case "INV-002":
            return MinimumReserveInvariant(spec)
        case "INV-003":
            return DryRunInvariant(spec, process)
        case "INV-004":
            return CommandRateInvariant(spec)
        case "INV-005":
            return SetpointBoundInvariant(spec)
        case "INV-006":
            return TelemetryIntegrityInvariant(spec)
        case _:
            msg = (
                f"no implementation registered for invariant {spec.id}; "
                f"safety invariants must be implemented in code, not inferred"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class InvariantStepResult:
    """Evaluation of the whole invariant set at one timestep."""

    t_s: float
    samples: tuple[InvariantSample, ...]

    @property
    def violated_ids(self) -> frozenset[str]:
        """Identifiers of invariants currently in a violated state."""
        return frozenset(s.invariant_id for s in self.samples if s.violated)

    @property
    def approaching_ids(self) -> frozenset[str]:
        """Identifiers of invariants currently within their warning margin."""
        return frozenset(
            s.invariant_id for s in self.samples if s.status is InvariantStatus.APPROACHING
        )

    @property
    def violated_count(self) -> int:
        """Number of invariants currently violated."""
        return len(self.violated_ids)


class InvariantEngine:
    """Evaluates every configured invariant once per timestep.

    A fresh engine is constructed per experiment. Invariants carry accumulated
    temporal state, so reusing one across runs would silently corrupt results.
    """

    def __init__(self, invariants_config: InvariantsConfig, process: ProcessConfig) -> None:
        """Build the invariant set from configuration."""
        self._invariants = build_invariants(invariants_config, process)
        self._evaluations: list[dict[str, Any]] = []

    @property
    def invariants(self) -> tuple[Invariant, ...]:
        """The configured invariant instances, in declaration order."""
        return tuple(self._invariants)

    def evaluate(self, state: ProcessState, dt_s: float) -> InvariantStepResult:
        """Evaluate all invariants against ``state``."""
        samples = tuple(inv.evaluate(state, dt_s) for inv in self._invariants)
        self._evaluations.extend(sample.as_dict() for sample in samples)
        return InvariantStepResult(t_s=state.t_s, samples=samples)

    def finalise(self, final_t_s: float) -> list[InvariantOutcome]:
        """Close open violation intervals and return per-invariant outcomes."""
        return [inv.finalise(final_t_s) for inv in self._invariants]

    def summary(self, final_t_s: float) -> dict[str, Any]:
        """Build the ``invariants.json`` payload for the evidence package."""
        outcomes = self.finalise(final_t_s)
        return {
            "evaluated_at_t_s": round(final_t_s, 3),
            "total_violations": sum(o.violation_count for o in outcomes),
            "violated_invariants": [o.invariant_id for o in outcomes if o.violated],
            "outcomes": [o.as_dict() for o in outcomes],
            "evaluations": list(self._evaluations),
        }
