"""Variant comparison.

The flagship result is a comparison: the same scenario, the same seed, the same
configuration, differing in exactly one respect -- whether the engineering
backstop is present. Everything reported here is a difference between two
measured runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blackstart.analysis.metrics import NOT_IMPLEMENTED
from blackstart.core.models import ConsequenceLevel
from blackstart.scenario_engine.orchestration import ExperimentResult

__all__ = ["ComparisonReport", "VariantRun", "compare_variants"]

# Metrics surfaced in the comparison table, with a display label and the
# direction that counts as an improvement.
_COMPARED_METRICS: tuple[tuple[str, str, str], ...] = (
    ("maximum_consequence", "Maximum consequence", "lower"),
    ("invariant_violations_total", "Invariant violations", "lower"),
    ("invariant_violation_duration_s", "Invariant violation duration (s)", "lower"),
    ("service_availability_pct", "Service availability (%)", "higher"),
    ("unsafe_state_duration_s", "Unsafe-state duration (s)", "lower"),
    ("max_tank_level_m", "Maximum tank level (m)", "lower"),
    ("max_deviation_from_setpoint_m", "Max deviation from setpoint (m)", "lower"),
    ("minimum_safety_margin_m", "Minimum safety margin (m)", "higher"),
    ("spill_volume_m3", "Spill volume (m3)", "lower"),
    ("supervisory_availability_pct", "Supervisory availability (%)", "higher"),
)


@dataclass(frozen=True, slots=True)
class VariantRun:
    """One completed variant of a comparison."""

    result: ExperimentResult
    metrics: dict[str, Any]

    @property
    def name(self) -> str:
        """The variant name."""
        return self.result.variant.name


@dataclass(slots=True)
class ComparisonReport:
    """Structured comparison of two or more variants of one scenario."""

    scenario_id: str
    scenario_name: str
    research_question: str
    seed: int
    runs: list[VariantRun]
    rows: list[dict[str, Any]]
    path_reduction: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise the comparison."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "research_question": self.research_question,
            "seed": self.seed,
            "variants": [
                {
                    "name": run.name,
                    "experiment_id": run.result.experiment_id,
                    "backstop_enabled": run.result.variant.backstop_enabled,
                    "configuration_hash": run.result.configuration_hash,
                }
                for run in self.runs
            ],
            "metrics": self.rows,
            "consequence_containment": self._containment(),
            "consequence_path_reduction": self.path_reduction,
        }

    def _containment(self) -> dict[str, Any] | None:
        """Report physical consequence reduction without hiding raw values."""
        by_name = {run.name: run.metrics for run in self.runs}
        before = by_name.get("backstop-disabled")
        after = by_name.get("backstop-enabled")
        if before is None or after is None:
            return None
        unsafe_before = float(before["unsafe_state_duration_s"])
        unsafe_after = float(after["unsafe_state_duration_s"])
        containment_pct: float | str
        if unsafe_before > 0:
            containment_pct = round(100.0 * (1.0 - unsafe_after / unsafe_before), 4)
        else:
            containment_pct = NOT_IMPLEMENTED
        return {
            "unsafe_state_duration_s": {
                "backstop_off": unsafe_before,
                "backstop_on": unsafe_after,
                "reduction_s": round(unsafe_before - unsafe_after, 4),
                "containment_pct": containment_pct,
            },
            "maximum_tank_level_m": {
                "backstop_off": before["max_tank_level_m"],
                "backstop_on": after["max_tank_level_m"],
                "reduction_m": round(
                    float(before["max_tank_level_m"]) - float(after["max_tank_level_m"]),
                    4,
                ),
            },
            "maximum_consequence": {
                "backstop_off": before["maximum_consequence"],
                "backstop_on": after["maximum_consequence"],
            },
        }

    def render(self) -> str:
        """Render the comparison as a plain-text table for the terminal."""
        names = [run.name for run in self.runs]
        width = max(len(name) for name in [*names, "Metric"]) + 2
        label_width = max(len(row["label"]) for row in self.rows) + 2

        lines = [
            "BLACKSTART EXP-BS-001 — BACKSTOP CONSEQUENCE CONTAINMENT",
            f"Scenario   {self.scenario_id} — {self.scenario_name}",
            f"Seed       {self.seed}",
            f"Question   {self.research_question}",
            "",
            "Metric".ljust(label_width) + "".join(name.ljust(width) for name in names),
            "-" * (label_width + width * len(names)),
        ]
        for row in self.rows:
            cells = "".join(str(row["values"][name]).ljust(width) for name in names)
            lines.append(row["label"].ljust(label_width) + cells)

        lines.append("")
        for run in self.runs:
            lines.append(f"{run.name:<22} {run.result.experiment_id}")
        containment = self._containment()
        if containment is not None:
            unsafe = containment["unsafe_state_duration_s"]
            level = containment["maximum_tank_level_m"]
            lines.extend(
                [
                    "",
                    "DELTA",
                    f"Unsafe-duration reduction  {unsafe['reduction_s']:.1f} s ",
                    f"Consequence containment    {unsafe['containment_pct']}%",
                    f"Max-level reduction         {level['reduction_m']:.4f} m",
                ]
            )
        return "\n".join(lines)


def compare_variants(
    runs: list[VariantRun], path_reduction: dict[str, Any] | None = None
) -> ComparisonReport:
    """Build a comparison report across variants of one scenario.

    Args:
        runs: Completed variant runs. All must be the same scenario and seed.
        path_reduction: Optional architectural consequence-path reduction, which
            is a property of the model rather than of these runs and is labelled
            as such in the output.

    Returns:
        The comparison report.

    Raises:
        ValueError: if fewer than two runs are supplied, or if they do not share
            a scenario and seed -- a comparison across different inputs would not
            isolate the variable under study.
    """
    if len(runs) < 2:
        msg = "a comparison requires at least two variant runs"
        raise ValueError(msg)

    scenarios = {run.result.scenario.id for run in runs}
    seeds = {run.result.seed for run in runs}
    if len(scenarios) != 1 or len(seeds) != 1:
        msg = (
            f"comparison requires one scenario and one seed; got scenarios "
            f"{sorted(scenarios)} and seeds {sorted(seeds)}"
        )
        raise ValueError(msg)

    reference = runs[0].result
    rows: list[dict[str, Any]] = []
    for key, label, better in _COMPARED_METRICS:
        values = {run.name: run.metrics.get(key, NOT_IMPLEMENTED) for run in runs}
        rows.append(
            {
                "metric": key,
                "label": label,
                "better": better,
                "values": values,
                "delta": _delta(key, values, better),
            }
        )

    return ComparisonReport(
        scenario_id=reference.scenario.id,
        scenario_name=reference.scenario.name,
        research_question=reference.scenario.research_question,
        seed=reference.seed,
        runs=list(runs),
        rows=rows,
        path_reduction=path_reduction,
    )


def _delta(key: str, values: dict[str, Any], better: str) -> dict[str, Any] | None:
    """Compute the change between exactly two variants, where meaningful."""
    if len(values) != 2:
        return None
    (_, first), (_, second) = values.items()

    if key == "maximum_consequence":
        try:
            before = ConsequenceLevel(first)
            after = ConsequenceLevel(second)
        except ValueError:
            return None
        return {
            "class_change": after.rank - before.rank,
            "improved": after.rank < before.rank,
        }

    if not isinstance(first, (int, float)) or not isinstance(second, (int, float)):
        return None
    change = float(second) - float(first)
    improved = change < 0 if better == "lower" else change > 0
    return {
        "absolute_change": round(change, 6),
        "improved": improved if change != 0 else None,
    }
