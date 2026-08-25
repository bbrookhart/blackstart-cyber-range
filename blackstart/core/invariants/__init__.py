"""Safety and mission invariants.

Invariants are BLACKSTART's ground-truth safety instrument: they evaluate what
physically happened, independently of what the control system believed and
independently of the engineering backstop. See ADR-004.
"""

from __future__ import annotations

from blackstart.core.invariants.base import (
    Invariant,
    InvariantOutcome,
    InvariantSample,
    Observation,
    ViolationInterval,
)
from blackstart.core.invariants.engine import (
    InvariantEngine,
    InvariantStepResult,
    build_invariants,
)

__all__ = [
    "Invariant",
    "InvariantEngine",
    "InvariantOutcome",
    "InvariantSample",
    "InvariantStepResult",
    "Observation",
    "ViolationInterval",
    "build_invariants",
]
