"""Independent recalculation of flagship metrics from exported CSV evidence.

This module deliberately does not import or call ``compute_metrics``. The
primary metrics engine works from in-memory domain objects; this verifier parses
the serialized process trace as an external reviewer would and independently
recalculates the four release-critical outcomes.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from blackstart.core.config import BlackstartConfig

__all__ = ["ResultVerification", "verify_results"]

_FLOAT_TOLERANCE = 1e-6


@dataclass(slots=True)
class ResultVerification:
    """Independent metric-check result."""

    experiment_id: str
    passed: bool = True
    primary: dict[str, Any] = field(default_factory=dict)
    independent: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, metric: str, expected: Any, observed: Any, ok: bool) -> None:
        """Record one comparison."""
        self.checks.append(
            {"metric": metric, "primary": expected, "independent": observed, "ok": ok}
        )
        if not ok:
            self.passed = False
            self.errors.append(f"{metric}: primary={expected!r}, independent={observed!r}")

    def as_dict(self) -> dict[str, Any]:
        """Serialise for ``verification.json`` and CLI output."""
        return {
            "experiment_id": self.experiment_id,
            "method": "independent CSV recalculation",
            "passed": self.passed,
            "tolerance": _FLOAT_TOLERANCE,
            "primary": self.primary,
            "independent": self.independent,
            "checks": self.checks,
            "errors": self.errors,
        }


def _close(left: Any, right: Any) -> bool:
    """Compare numerics within tolerance and other values exactly."""
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= _FLOAT_TOLERANCE
    return bool(left == right)


def verify_results(directory: Path) -> ResultVerification:
    """Recalculate key metrics from ``process.csv`` and compare to ``metrics.json``.

    Raises:
        FileNotFoundError: if a required artifact is absent.
        ValueError: if an artifact is empty or structurally invalid.
    """
    process_path = directory / "process.csv"
    metrics_path = directory / "metrics.json"
    configuration_path = directory / "configuration.json"
    for path in (process_path, metrics_path, configuration_path):
        if not path.is_file():
            raise FileNotFoundError(f"required result artifact is missing: {path}")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    config = BlackstartConfig.model_validate(configuration["config"])
    experiment_id = str(metrics.get("experiment_id", directory.name))

    with process_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{process_path}: process trace is empty")

    maximum_safe_m = config.invariants.by_id("INV-001").limit_m
    minimum_safe_m = config.invariants.by_id("INV-002").limit_m
    if maximum_safe_m is None or minimum_safe_m is None:
        raise ValueError("INV-001 and INV-002 limits are required for independent verification")

    levels = [float(row["true_tank_level_m"]) for row in rows]
    timestep_s = float(metrics["timestep_s"])
    unsafe_steps = sum(1 for level in levels if level > maximum_safe_m or level < minimum_safe_m)

    previous: set[str] = set()
    interval_count = 0
    maximum_consequence_rank = 0
    for row in rows:
        active = {item for item in row["violated_invariants"].split("|") if item}
        interval_count += len(active - previous)
        previous = active
        level = row["consequence_level"]
        if len(level) != 2 or not level.startswith("C") or not level[1].isdigit():
            raise ValueError(f"invalid consequence level in process.csv: {level!r}")
        maximum_consequence_rank = max(maximum_consequence_rank, int(level[1]))

    independent = {
        "max_tank_level_m": round(max(levels), 4),
        "unsafe_state_duration_s": round(unsafe_steps * timestep_s, 3),
        "invariant_violations_total": interval_count,
        "maximum_consequence": f"C{maximum_consequence_rank}",
    }
    primary = {key: metrics[key] for key in independent}
    report = ResultVerification(
        experiment_id=experiment_id,
        primary=primary,
        independent=independent,
    )
    for key, observed in independent.items():
        report.add(key, primary[key], observed, _close(primary[key], observed))
    return report
