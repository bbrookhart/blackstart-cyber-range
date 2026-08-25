"""Scenario engine: declarative scenarios, a closed effect registry, and the runner.

Scenarios are data, not code. The effect vocabulary is closed. Neither this
package nor :mod:`blackstart.core` can reach outside the Python process. See
ADR-006 for why that boundary is structural rather than a policy statement.
"""

from __future__ import annotations

from blackstart.scenario_engine.effects import EFFECT_REGISTRY, resolve_effect
from blackstart.scenario_engine.loader import list_scenarios, load_scenario, load_scenario_file
from blackstart.scenario_engine.orchestration import (
    VARIANTS,
    ExperimentResult,
    ExperimentRunner,
    Variant,
    resolve_variant,
)
from blackstart.scenario_engine.schema import Scenario, ScenarioEvent

__all__ = [
    "EFFECT_REGISTRY",
    "VARIANTS",
    "ExperimentResult",
    "ExperimentRunner",
    "Scenario",
    "ScenarioEvent",
    "Variant",
    "list_scenarios",
    "load_scenario",
    "load_scenario_file",
    "resolve_effect",
    "resolve_variant",
]
