"""EXP-BS-001 controlled comparison and release-artifact generation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blackstart.analysis.compare import VariantRun, compare_variants
from blackstart.analysis.metrics import compute_metrics
from blackstart.analysis.plots import render_consequence_path, render_flagship_figures
from blackstart.analysis.verification import verify_results
from blackstart.core.config import BlackstartConfig
from blackstart.core.graph.build import build_graph, load_asset_model
from blackstart.core.graph.queries import path_reduction
from blackstart.evidence.package import write_evidence
from blackstart.evidence.verify import verify_evidence
from blackstart.scenario_engine.loader import load_scenario
from blackstart.scenario_engine.orchestration import (
    ExperimentResult,
    ExperimentRunner,
    resolve_variant,
)

__all__ = ["FlagshipRelease", "run_flagship"]

_SCENARIO_ID = "SCN-004"


@dataclass(frozen=True, slots=True)
class FlagshipRelease:
    """Locations and measured values produced by EXP-BS-001."""

    output_directory: Path
    unprotected_directory: Path
    protected_directory: Path
    comparison_path: Path
    report_path: Path
    figures: dict[str, Path]
    runs: tuple[VariantRun, VariantRun]
    comparison: dict[str, Any]


def _run_condition(
    config: BlackstartConfig,
    variant_name: str,
    evidence_root: Path,
) -> tuple[VariantRun, Path]:
    """Execute, package, integrity-check, and independently verify one condition."""
    scenario = load_scenario(_SCENARIO_ID)
    result: ExperimentResult = ExperimentRunner(
        config, scenario, resolve_variant(variant_name)
    ).run()
    metrics = compute_metrics(result, config)
    result.metrics = metrics
    directory = write_evidence(result, config, metrics, evidence_root)
    evidence_report = verify_evidence(directory)
    if not evidence_report.passed:
        raise ValueError("evidence verification failed: " + "; ".join(evidence_report.errors))
    result_report = verify_results(directory)
    if not result_report.passed:
        raise ValueError("result verification failed: " + "; ".join(result_report.errors))
    return VariantRun(result=result, metrics=metrics), directory


def _difference(before: Any, after: Any, *, better: str) -> str:
    """Format a measured difference without inventing arithmetic for ordinals."""
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        change = float(after) - float(before)
        if better == "lower":
            return f"{abs(change):.4f} reduction" if change < 0 else f"+{change:.4f}"
        return f"+{change:.4f} improvement" if change > 0 else f"{change:.4f}"
    if before == after:
        return "no change"
    return f"{before} → {after}"


def _results_table(off: dict[str, Any], on: dict[str, Any]) -> str:
    """Render the canonical Markdown results table from metrics JSON values."""
    rows = (
        ("Maximum tank level", "max_tank_level_m", "m", "lower"),
        ("Unsafe duration", "unsafe_state_duration_s", "s", "lower"),
        ("Invariant violation intervals", "invariant_violations_total", "", "lower"),
        ("Invariant violation duration", "invariant_violation_duration_s", "s", "lower"),
        ("Maximum consequence", "maximum_consequence", "", "lower"),
        ("Mission service availability", "service_availability_pct", "%", "higher"),
        ("Recovery time", "recovery_time_s", "", "lower"),
    )
    lines = [
        "| Metric | Backstop OFF | Backstop ON | Difference |",
        "| --- | ---: | ---: | --- |",
    ]
    for label, key, unit, better in rows:
        before = off[key]
        after = on[key]
        before_text = f"{before} {unit}".strip()
        after_text = f"{after} {unit}".strip()
        lines.append(
            f"| {label} | {before_text} | {after_text} | "
            f"{_difference(before, after, better=better)} |"
        )
    return "\n".join(lines)


def _update_readme_results(readme_path: Path, table: str) -> None:
    """Replace the generated README result card between stable markers."""
    start = "<!-- BEGIN GENERATED EXP-BS-001 RESULTS -->"
    end = "<!-- END GENERATED EXP-BS-001 RESULTS -->"
    text = readme_path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{readme_path} must contain exactly one generated-results marker pair")
    before, remainder = text.split(start, maxsplit=1)
    _, after = remainder.split(end, maxsplit=1)
    generated = f"{start}\n\n### Flagship experiment — EXP-BS-001\n\n{table}\n\n{end}"
    readme_path.write_text(before + generated + after, encoding="utf-8")


def _render_report(
    off: VariantRun,
    on: VariantRun,
    comparison: dict[str, Any],
    table: str,
) -> str:
    """Render the evidence-backed EXP-BS-001 technical report."""
    off_metrics, on_metrics = off.metrics, on.metrics
    containment = comparison["consequence_containment"]["unsafe_state_duration_s"]
    return f"""# BLACKSTART: Experimental Evaluation of an Engineering Backstop Under Simulated Supervisory Control Compromise

## Abstract

BLACKSTART evaluated whether an independently enforced engineering backstop can
prevent a simulated unauthorized supervisory setpoint mutation from producing an
unacceptable physical consequence in a deterministic synthetic water-storage
process. The unprotected condition reached **{off_metrics["maximum_consequence"]}**,
remained outside the physical safety envelope for
**{off_metrics["unsafe_state_duration_s"]:.1f} s**, and reached
**{off_metrics["max_tank_level_m"]:.4f} m**. Under identical initial state,
demand, seed, timestep, and attack event, the protected condition reached
**{on_metrics["maximum_consequence"]}**, recorded
**{on_metrics["unsafe_state_duration_s"]:.1f} s** unsafe, and peaked at
**{on_metrics["max_tank_level_m"]:.4f} m**. This is a result about the documented
synthetic model—not a claim of protection for an operational water system.

## Research Question

> If an adversary is assumed capable of modifying a critical control parameter
> after penetrating portions of the digital environment, can an independently
> enforced engineering backstop prevent that digital compromise from producing
> an unacceptable physical consequence?

## Hypothesis

**H1:** An independently enforced cyber-physical backstop will significantly
reduce or eliminate unacceptable physical consequences caused by an unauthorized
control-state mutation.

**H0:** The backstop produces no meaningful difference in physical consequence
under the defined experiment.

## Background

The experiment applies consequence-driven, cyber-informed engineering logic:
assume the supervisory command path can be compromised, preserve the critical
physical mission through an independently enforced engineering constraint, and
measure the complete cyber-to-consequence chain.

## Threat Model

At **t = {off.result.scenario.events[0].t_s:.1f} s**, a controlled internal event
sets the requested tank-level target to
**{off.result.scenario.events[0].params["value_m"]:.2f} m**. No exploit chain,
credential theft, malware delivery, network penetration, or PLC exploitation is
implemented. The supervisory requested state is untrusted. The physics engine,
experiment orchestrator, backstop policy, and evidence verifier are trusted.

## Process Model

The fictional process contains one source, inlet pump, constant-area storage
tank, and gravity outlet. Explicit Euler integration uses a **{off.result.timestep_s:.1f} s**
timestep. All values are synthetic; equations, units, saturation, and numerical
assumptions are documented in `docs/physical-model.md`.

## Engineering Backstop

EBS-001 sits between the requested supervisory state and the effective control
value. BS-01 clamps the effective setpoint to the configured engineering
envelope before the level controller acts. BS-02 bounds setpoint slew. Separate
permissives provide high-level trip, suction protection, and anti-cycling. The
scenario can mutate the supervisory request but cannot mutate the backstop policy.

## Safety Invariants

INV-001 bounds maximum level; INV-002 maintains minimum reserve; INV-003 protects
against dry run; INV-004 records an implausible requested command rate; INV-005
bounds the effective setpoint; INV-006 detects truth/reported-state divergence.
Every evaluation is preserved in `invariants.json`.

## Experiment Design

- Experiment: **EXP-BS-001-v1**
- Scenario: **SCN-004 — Unauthorized Setpoint Mutation**
- Seed: **{off.result.seed}**
- Duration: **{off.result.duration_s:.1f} s**
- Condition A: backstop OFF
- Condition B: backstop ON
- Controlled variable: backstop state only
- Source fingerprint: `{off.result.source_fingerprint}`

## Metrics

Metrics are derived from the process trace. Four release-critical metrics are
recalculated by a second implementation that reads only `process.csv`; the
comparison is recorded in `verification.json`.

## Results

{table}

Unsafe-state duration fell by **{containment["reduction_s"]:.1f} s**
(**{containment["containment_pct"]:.1f}% consequence containment** for this
physical metric). The requested 4.80 m mutation remains present in both traces;
the protected result comes from constraining its physical influence, not deleting
the adversary event.

## Figures

![Physical trajectory](figures/exp-bs-001-trajectory.svg)

![Requested versus effective control](figures/exp-bs-001-control.svg)

![Safety margin](figures/exp-bs-001-safety-margin.svg)

## Analysis

The observed deterministic result is inconsistent with H0 for the documented
synthetic configuration: the protected and unprotected physical trajectories
differ materially while all inputs except backstop state remain identical. No
statistical significance claim is made. The evidence supports the narrow
claim that EBS-001 prevented the tested supervisory mutation from producing the
physical consequence observed without it.

## Threats to Validity

**Construct validity.** The model represents storage, pump inflow, gravity
outflow, demand, saturation, and control behavior, but it is not a calibrated
model of a real facility.

**Internal validity.** The two conditions share scenario, seed, initial state,
demand sequence, timestep, and code fingerprint. Only backstop state differs.

**External validity.** Generalization to operational OT systems is **not yet
established**. The independent backstop and sensor separation are modeled
assumptions, not field-validated properties.

**Reproducibility.** Evidence hashes, deterministic replay, independent metric
calculation, and the one-command reproduction script test whether another
researcher can obtain equivalent trajectories.

## Limitations

- simplified physical process and synthetic telemetry;
- fictional utility and no production infrastructure;
- no real PLC, hardware-in-the-loop, or utility network;
- no real adversary or exploit chain;
- assumed supervisory compromise;
- backstop outside the modeled compromise;
- one flagship compromise scenario;
- no claim of certification, compliance, or operational safety.

## Reproducibility

```bash
make bootstrap
make test
make experiment
```

The individual evidence packages are `{off.result.experiment_id}` and
`{on.result.experiment_id}`. Run `blackstart evidence verify` and
`blackstart experiment verify-results` against each directory.

## Future Work

The next experiment should test sensor-state manipulation against the same
frozen process and backstop, without broadening sectors or adding hardware until
the new causal claim is equally reproducible.
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def run_flagship(
    config: BlackstartConfig,
    *,
    evidence_root: Path,
    output_directory: Path,
    assets_directory: Path | None = None,
    technical_report_path: Path | None = None,
    readme_path: Path | None = None,
    review_directory: Path | None = None,
) -> FlagshipRelease:
    """Run both conditions and generate the complete EXP-BS-001 result."""
    output_directory.mkdir(parents=True, exist_ok=True)
    off, off_directory = _run_condition(config, "backstop-disabled", evidence_root)
    on, on_directory = _run_condition(config, "backstop-enabled", evidence_root)

    graph = build_graph(load_asset_model(), config.invariants, config.consequences)
    report = compare_variants(
        [off, on], path_reduction=path_reduction(graph, minimum_class="C4").as_dict()
    )
    comparison = report.as_dict()
    comparison["experiment"] = "EXP-BS-001-v1"
    comparison["evidence"] = {
        "backstop_off": str(off_directory),
        "backstop_on": str(on_directory),
    }
    comparison_path = output_directory / "comparison.json"
    comparison_path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    figures = render_flagship_figures(off_directory, on_directory, output_directory / "figures")
    graph_document = json.loads((off_directory / "graph.json").read_text(encoding="utf-8"))
    figures["consequence_path"] = render_consequence_path(
        graph_document, output_directory / "figures" / "consequence-path.svg"
    )
    table = _results_table(off.metrics, on.metrics)
    (output_directory / "results-table.md").write_text(table + "\n", encoding="utf-8")
    report_path = output_directory / "report.md"
    report_text = _render_report(off, on, comparison, table)
    report_path.write_text(report_text, encoding="utf-8")
    (output_directory / "README-results.md").write_text(
        "## Flagship experiment — EXP-BS-001\n\n" + table + "\n",
        encoding="utf-8",
    )
    if readme_path is not None:
        _update_readme_results(readme_path, table)
    if review_directory is not None:
        review_directory.mkdir(parents=True, exist_ok=True)
        figure_directory = review_directory / "figures"
        figure_directory.mkdir(parents=True, exist_ok=True)
        for path in figures.values():
            shutil.copy2(path, figure_directory / path.name)
        with (review_directory / "results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["metric", "unit", "backstop_off", "backstop_on"])
            for label, key, unit in (
                ("Maximum tank level", "max_tank_level_m", "m"),
                ("Unsafe duration", "unsafe_state_duration_s", "s"),
                ("Invariant violation intervals", "invariant_violations_total", "count"),
                ("Invariant violation duration", "invariant_violation_duration_s", "s"),
                ("Maximum consequence", "maximum_consequence", "class"),
                ("Mission service availability", "service_availability_pct", "percent"),
                ("Recovery time", "recovery_time_s", "status_or_seconds"),
            ):
                writer.writerow([label, unit, off.metrics[key], on.metrics[key]])

    if assets_directory is not None:
        assets_directory.mkdir(parents=True, exist_ok=True)
        for path in figures.values():
            shutil.copy2(path, assets_directory / path.name)
    if technical_report_path is not None:
        technical_report_path.parent.mkdir(parents=True, exist_ok=True)
        technical_text = report_text
        if assets_directory is None:
            report_figure_directory = technical_report_path.parent / "figures"
            report_figure_directory.mkdir(parents=True, exist_ok=True)
            for path in figures.values():
                shutil.copy2(path, report_figure_directory / path.name)
            figure_base = report_figure_directory
        else:
            figure_base = assets_directory
        for path in figures.values():
            relative = Path(
                os.path.relpath(figure_base / path.name, technical_report_path.parent)
            ).as_posix()
            technical_text = technical_text.replace(f"(figures/{path.name})", f"({relative})")
        technical_report_path.write_text(technical_text, encoding="utf-8")

    release_files = [
        comparison_path,
        report_path,
        output_directory / "results-table.md",
        *figures.values(),
    ]
    manifest = {
        "release": "v0.1.0",
        "experiment": "EXP-BS-001-v1",
        "source_fingerprint": off.result.source_fingerprint,
        "artifacts": {
            str(path.relative_to(output_directory)): {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in release_files
        },
    }
    (output_directory / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return FlagshipRelease(
        output_directory=output_directory,
        unprotected_directory=off_directory,
        protected_directory=on_directory,
        comparison_path=comparison_path,
        report_path=report_path,
        figures=figures,
        runs=(off, on),
        comparison=comparison,
    )
