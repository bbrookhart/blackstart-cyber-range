"""Evidence package writer.

Every experiment produces a self-describing directory that lets a reviewer
understand exactly what happened without running anything:

.. code-block:: text

    EXP-.../
    |-- manifest.json      provenance, seed, config hash, artefact digests
    |-- configuration.json fully resolved configuration actually executed
    |-- events.jsonl       ordered structured event stream
    |-- process.csv        per-timestep true and reported physical state
    |-- invariants.json    per-invariant outcome and violation intervals
    |-- consequences.json  consequence timeline and maximum severity
    |-- metrics.json       computed research metrics
    `-- summary.md         human-readable account of the run

Integrity is **tamper-evidence, not tamper-proofing.** The manifest records a
SHA-256 for every artefact and a digest over the sorted artefact list. Anyone who
can edit the artefacts can recompute the manifest. This defends against
accidental corruption, partial writes and stale files; it does not defend against
a motivated forger, and ADR-005 says so rather than implying otherwise.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from blackstart.core.config import BlackstartConfig, canonical_json
from blackstart.scenario_engine.orchestration import ExperimentResult
from blackstart.telemetry.exporters.csv_exporter import write_process_csv
from blackstart.telemetry.exporters.jsonl import write_events_jsonl

__all__ = ["ARTIFACT_NAMES", "MANIFEST_NAME", "integrity_digest", "write_evidence"]

MANIFEST_NAME = "manifest.json"

#: Exactly the files an evidence package must contain, besides the manifest.
#: Verification fails on a missing file *or* an unexpected extra one.
ARTIFACT_NAMES: tuple[str, ...] = (
    "configuration.json",
    "events.jsonl",
    "process.csv",
    "invariants.json",
    "consequences.json",
    "metrics.json",
    "summary.md",
)


def _sha256_file(path: Path) -> str:
    """Compute the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integrity_digest(artifacts: dict[str, dict[str, Any]]) -> str:
    """Compute the top-level digest over the sorted artefact digest list."""
    material = [(name, meta["sha256"]) for name, meta in sorted(artifacts.items())]
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    """Write a canonical JSON document with a trailing newline."""
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def write_evidence(
    result: ExperimentResult,
    config: BlackstartConfig,
    metrics: dict[str, Any],
    evidence_root: Path,
) -> Path:
    """Write the complete evidence package for one experiment.

    Args:
        result: The completed experiment.
        config: The configuration it ran under.
        metrics: Computed research metrics.
        evidence_root: Directory under which the experiment directory is created.

    Returns:
        Path to the experiment's evidence directory.
    """
    directory = evidence_root / result.experiment_id
    directory.mkdir(parents=True, exist_ok=True)

    _write_json(
        directory / "configuration.json",
        {
            "config": config.model_dump(mode="json"),
            "scenario": result.scenario.model_dump(mode="json"),
            "variant": {
                "name": result.variant.name,
                "backstop_enabled": result.variant.backstop_enabled,
                "description": result.variant.description,
            },
            "seed": result.seed,
            "configuration_hash": result.configuration_hash,
        },
    )
    write_events_jsonl(result.events.events, directory / "events.jsonl")
    write_process_csv(result.trace.rows, directory / "process.csv")
    _write_json(directory / "invariants.json", result.invariants)
    _write_json(
        directory / "consequences.json",
        {
            **result.consequences.as_dict(),
            "critical_function": config.consequences.critical_function.model_dump(mode="json"),
        },
    )
    _write_json(directory / "metrics.json", metrics)
    (directory / "summary.md").write_text(
        _render_summary(result, config, metrics), encoding="utf-8"
    )

    artifacts = {
        name: {
            "sha256": _sha256_file(directory / name),
            "bytes": (directory / name).stat().st_size,
        }
        for name in ARTIFACT_NAMES
    }

    manifest: dict[str, Any] = {
        "experiment_id": result.experiment_id,
        "blackstart_version": result.blackstart_version,
        "scenario": {
            "id": result.scenario.id,
            "name": result.scenario.name,
            "category": result.scenario.category,
            "research_question": result.scenario.research_question,
        },
        "variant": {
            "name": result.variant.name,
            "backstop_enabled": result.variant.backstop_enabled,
        },
        "determinism": {
            "seed": result.seed,
            "configuration_hash": result.configuration_hash,
            "timestep_s": result.timestep_s,
            "duration_s": result.duration_s,
            "steps": result.step_count,
        },
        "result": {
            "maximum_consequence": result.maximum_consequence.value,
            "violated_invariants": result.violated_invariants,
            "service_availability_pct": metrics["service_availability_pct"],
            "unsafe_state_duration_s": metrics["unsafe_state_duration_s"],
        },
        # Provenance is wall-clock and environment metadata. It is deliberately
        # EXCLUDED from the integrity digest so that re-running an experiment
        # reproduces every artefact byte-for-byte (ADR-005).
        "provenance": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "artifacts": artifacts,
        "integrity": {
            "algorithm": "sha256",
            "scope": "artifact digests only; provenance excluded",
            "digest": integrity_digest(artifacts),
        },
    }
    # The manifest is written with indentation: it is the file a reviewer reads.
    (directory / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return directory


def _render_summary(
    result: ExperimentResult, config: BlackstartConfig, metrics: dict[str, Any]
) -> str:
    """Render the human-readable ``summary.md`` for an experiment."""
    scenario = result.scenario
    inv_lines = []
    for outcome in result.invariants["outcomes"]:
        status = "VIOLATED" if outcome["violated"] else "ok"
        detail = ""
        if outcome["violated"]:
            detail = (
                f" — {outcome['violation_count']} interval(s), "
                f"{outcome['total_violation_s']:.1f} s total, "
                f"first at t={outcome['first_violation_t_s']:.1f} s, "
                f"peak {outcome['peak_excursion']:.3f}"
            )
        elif outcome["total_approaching_s"] > 0:
            detail = f" — approached limit for {outcome['total_approaching_s']:.1f} s"
        inv_lines.append(f"| {outcome['invariant_id']} | {outcome['name']} | {status} |{detail} |")

    event_lines = [
        f"| {event.t_s:.1f} | `{event.effect}` | {event.description} |" for event in scenario.events
    ] or ["| — | — | No scenario events; nominal operation. |"]

    backstop = result.backstop
    activations = ", ".join(
        f"{rule}={count}" for rule, count in sorted(backstop["activation_counts"].items())
    )
    recovery = metrics["recovery"]

    return f"""# Experiment {result.experiment_id}

**Scenario:** {scenario.id} — {scenario.name}
**Variant:** {result.variant.name} ({result.variant.description})
**Seed:** {result.seed} · **Configuration hash:** `{result.configuration_hash[:16]}…`
**BLACKSTART version:** {result.blackstart_version}

## Research question

> {scenario.research_question}

## What was simulated

{scenario.description}

| t (s) | Effect | Description |
| --- | --- | --- |
{chr(10).join(event_lines)}

## Measured result

| Metric | Value |
| --- | --- |
| Maximum consequence | **{metrics["maximum_consequence"]}** |
| Invariant violations | **{metrics["invariant_violations_total"]}** |
| Violated invariants | {", ".join(metrics["violated_invariants"]) or "none"} |
| Service availability | {metrics["service_availability_pct"]:.2f}% |
| Unsafe-state duration | {metrics["unsafe_state_duration_s"]:.1f} s \
({metrics["unsafe_state_pct"]:.1f}% of run) |
| Maximum tank level | {metrics["max_tank_level_m"]:.3f} m \
(safe limit {config.invariants.by_id("INV-001").limit_m:.2f} m) |
| Minimum tank level | {metrics["min_tank_level_m"]:.3f} m \
(reserve {config.invariants.by_id("INV-002").limit_m:.2f} m) |
| Max deviation from legitimate setpoint | {metrics["max_deviation_from_setpoint_m"]:.3f} m |
| Spill volume | {metrics["spill_volume_m3"]:.3f} m³ |
| Supervisory availability | {metrics["supervisory_availability_pct"]:.2f}% |
| Pump starts | {metrics["pump_starts"]} |
| Recovery | {recovery["status"]}\
{"" if recovery["recovery_time_s"] is None else f" ({recovery['recovery_time_s']:.1f} s)"} |

## Safety invariants

| ID | Name | Status | Detail |
| --- | --- | --- | --- |
{chr(10).join(inv_lines)}

## Engineering backstop

Backstop **{"enabled" if backstop["enabled"] else "disabled"}** for this run.

Rule activations: {activations}

High-level trip count: {backstop["trip"]["trip_count"]}\
{
        ""
        if backstop["trip"]["first_trip_t_s"] is None
        else f", first at t={backstop['trip']['first_trip_t_s']:.1f} s"
    }

A rule showing zero activations did not act in this experiment. BS-05 is
redundant with the controller's own anti-cycling under the shipped scenarios and
is expected to read zero.

## Reproducing this experiment

```bash
uv run blackstart experiment run {scenario.id} --variant {result.variant.name}
uv run blackstart evidence verify {result.experiment_id}
```

The experiment identifier is derived from the configuration hash, so an
identical run reproduces this package byte-for-byte.

## Limitations

This is a simulation result. It describes the behaviour of the BLACKSTART model
under the stated configuration and seed. It does not establish how any real
water utility, control system, or piece of equipment would behave. See
`docs/limitations.md`.

Detection and containment latency are reported as `NOT_IMPLEMENTED`: BLACKSTART
v0.1 emits no network telemetry and runs no detection analytic, so those metrics
have no basis.
"""
