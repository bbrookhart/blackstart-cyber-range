"""Scenario loading and validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from blackstart.scenario_engine.effects import resolve_effect
from blackstart.scenario_engine.schema import Scenario

__all__ = ["DEFAULT_SCENARIO_DIR", "list_scenarios", "load_scenario", "load_scenario_file"]

DEFAULT_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"


def load_scenario_file(path: Path) -> Scenario:
    """Load and fully validate one scenario document.

    Validation is two-stage: the Pydantic schema checks structure, then every
    event's effect name is resolved against the closed registry and its
    parameters are validated by the effect itself. A scenario that would fail at
    runtime therefore fails at load time instead.

    Args:
        path: Path to the scenario YAML file.

    Returns:
        The validated scenario.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the document is malformed, names an unknown effect, or
            supplies invalid effect parameters.
    """
    if not path.is_file():
        msg = f"scenario file not found: {path}"
        raise FileNotFoundError(msg)

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        msg = f"expected a YAML mapping at the top level of {path}"
        raise ValueError(msg)

    scenario = Scenario.model_validate(document)

    for event in scenario.events:
        effect = resolve_effect(event.effect)
        try:
            effect.validate_params(event.params)
        except ValueError as exc:
            msg = f"{scenario.id}: invalid parameters for effect '{event.effect}': {exc}"
            raise ValueError(msg) from exc

    if scenario.id != path.stem:
        msg = (
            f"scenario id '{scenario.id}' does not match filename '{path.stem}'; "
            f"identifiers must be resolvable from the filename alone"
        )
        raise ValueError(msg)

    return scenario


def list_scenarios(scenario_dir: Path | None = None) -> list[Scenario]:
    """Load every scenario in a directory, ordered by identifier."""
    directory = scenario_dir if scenario_dir is not None else DEFAULT_SCENARIO_DIR
    return [load_scenario_file(path) for path in sorted(directory.glob("SCN-*.yaml"))]


def load_scenario(scenario_id: str, scenario_dir: Path | None = None) -> Scenario:
    """Load a scenario by identifier such as ``SCN-004``.

    Raises:
        FileNotFoundError: if no scenario with that identifier exists, listing
            the identifiers that do.
    """
    directory = scenario_dir if scenario_dir is not None else DEFAULT_SCENARIO_DIR
    path = directory / f"{scenario_id}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in directory.glob("SCN-*.yaml")))
        msg = f"unknown scenario '{scenario_id}'. Available: {available or '(none)'}"
        raise FileNotFoundError(msg)
    return load_scenario_file(path)
