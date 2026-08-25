"""Scenario schema.

A scenario is declarative data. It contains no expressions, no code, no imports
and no file paths, and loading one cannot execute anything. Every event names an
effect from the closed registry in :mod:`blackstart.scenario_engine.effects`; an
unknown effect name is a load-time validation error rather than a dynamic
dispatch (ADR-006).

That structure is what makes the safety boundary testable rather than
aspirational: widening it requires editing reviewed Python and deleting a test.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["Scenario", "ScenarioEvent", "ScenarioExpectation", "VariantExpectations"]

#: Shape of an ATT&CK technique or sub-technique identifier.
_ATTACK_ID_PATTERN = re.compile(r"T\d{4}(\.\d{3})?")


class _Frozen(BaseModel):
    """Immutable, strictly validated scenario model."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ScenarioEvent(_Frozen):
    """One controlled change applied to the simulated environment."""

    t_s: float = Field(ge=0.0, description="Simulation time at which the effect activates.")
    effect: str = Field(description="Name from the closed effect registry.")
    description: str
    #: When set, the effect is reverted at ``t_s + duration_s``. Absent means the
    #: effect persists to the end of the experiment.
    duration_s: float | None = Field(default=None, gt=0.0)
    params: dict[str, Any] = Field(default_factory=dict)
    #: MITRE ATT&CK for ICS technique identifiers, where a defensible mapping
    #: exists for the *simulated behaviour*. Optional and frequently empty:
    #: a benign physical disturbance maps to nothing, and saying so is the point.
    #: Mappings and their rationale live in framework-mappings/attack-ics.yaml.
    attack_ics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _attack_ids_well_formed(self) -> Self:
        """Reject malformed ATT&CK identifiers.

        Both numbering forms are accepted. Several ICS techniques were
        renumbered from the ``T0xxx`` series into ``T1xxx`` parent/sub-technique
        pairs upstream (for example the former ``T0855`` is now
        ``T1692.001``), so a validator that only accepted ``T0`` would reject
        currently correct identifiers.

        This checks shape only. Whether an identifier actually exists, and
        whether the mapping is defensible, is recorded with a retrieval date in
        ``framework-mappings/attack-ics.yaml``.
        """
        for technique in self.attack_ics:
            if not _ATTACK_ID_PATTERN.fullmatch(technique):
                msg = (
                    f"'{technique}' is not a well-formed ATT&CK for ICS technique id "
                    f"(expected Tnnnn or Tnnnn.nnn); fabricated identifiers are worse "
                    f"than no mapping"
                )
                raise ValueError(msg)
        return self

    @property
    def end_t_s(self) -> float | None:
        """Simulation time at which this effect is reverted, if bounded."""
        return None if self.duration_s is None else self.t_s + self.duration_s


class ScenarioExpectation(_Frozen):
    """Expected outcome for one experiment variant.

    Populated from *measured* results and asserted by the integration suite. A
    divergence means either the implementation regressed or the design intent
    was wrong; both require investigation rather than an updated number.
    """

    maximum_consequence: str = Field(pattern=r"^C[0-5]$")
    violated_invariants: list[str] = Field(default_factory=list)
    #: Tolerance band on service availability, as a percentage.
    service_availability_pct_min: float | None = Field(default=None, ge=0.0, le=100.0)
    service_availability_pct_max: float | None = Field(default=None, ge=0.0, le=100.0)


class VariantExpectations(_Frozen):
    """Expected outcomes for each backstop configuration."""

    backstop_disabled: ScenarioExpectation
    backstop_enabled: ScenarioExpectation


class Scenario(_Frozen):
    """A complete, reproducible scenario definition."""

    id: str = Field(pattern=r"^SCN-\d{3}$")
    name: str
    description: str
    #: The question this scenario is designed to answer. Every scenario must have
    #: one; a scenario that answers no question is a demonstration, not research.
    research_question: str
    category: Literal["baseline", "physical-disturbance", "cyber-effect", "operational"]
    seed: int = Field(ge=0)
    duration_s: float = Field(gt=0.0)
    events: list[ScenarioEvent] = Field(default_factory=list)
    expected: VariantExpectations | None = None
    #: Free-form notes on interpretation and known caveats for this scenario.
    notes: str | None = None

    @model_validator(mode="after")
    def _events_within_duration(self) -> Self:
        for event in self.events:
            if event.t_s >= self.duration_s:
                msg = (
                    f"{self.id}: event '{event.effect}' activates at t={event.t_s}s, "
                    f"at or beyond the scenario duration ({self.duration_s}s)"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _events_ordered(self) -> Self:
        times = [event.t_s for event in self.events]
        if times != sorted(times):
            msg = f"{self.id}: events must be listed in ascending activation order"
            raise ValueError(msg)
        return self

    def causal_fingerprint(self) -> dict[str, Any]:
        """Return only the scenario fields that determine the experiment outcome.

        The configuration hash is built from this rather than from the whole
        document. Prose (``name``, ``description``, ``research_question``,
        ``notes``), framework mappings, and the ``expected`` block are all
        excluded: they are documentation and assertions *about* a result, not
        inputs *to* it.

        Including them would mean that correcting a typo in a description, or
        recording a measured expectation, silently invalidates every experiment
        identifier for that scenario -- which would train a reader to ignore
        identifier changes, exactly the opposite of what the hash is for.
        """
        return {
            "id": self.id,
            "seed": self.seed,
            "duration_s": self.duration_s,
            "events": [
                {
                    "t_s": event.t_s,
                    "effect": event.effect,
                    "duration_s": event.duration_s,
                    "params": event.params,
                }
                for event in self.events
            ],
        }

    @property
    def attack_ics_techniques(self) -> list[str]:
        """Every ATT&CK for ICS technique referenced by this scenario."""
        seen: list[str] = []
        for event in self.events:
            for technique in event.attack_ics:
                if technique not in seen:
                    seen.append(technique)
        return seen
