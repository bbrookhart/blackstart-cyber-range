"""Evidence verification and independent reproduction.

Two levels of check, in increasing strength:

``verify``
    Recompute every artefact digest and the top-level integrity digest, and
    confirm the package contains exactly the expected files. Catches corruption,
    partial writes, stale files and accidental edits.

``reproduce``
    Re-execute the experiment from the configuration and seed recorded in the
    package, and compare the freshly produced artefacts against the stored ones.
    This is the strongest reproducibility claim BLACKSTART v0.1 makes: it
    demonstrates that the recorded result is a function of the recorded inputs.

Neither is proof against a motivated forger; see ADR-005.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from blackstart.core.config import BlackstartConfig
from blackstart.evidence.package import (
    ARTIFACT_NAMES,
    MANIFEST_NAME,
    _sha256_file,
    integrity_digest,
    write_evidence,
)
from blackstart.evidence.schema import (
    EnvironmentDocument,
    EventEnvelope,
    ManifestDocument,
    VerificationDocument,
)
from blackstart.scenario_engine.orchestration import ExperimentRunner, resolve_variant
from blackstart.scenario_engine.schema import Scenario

__all__ = ["VerificationReport", "reproduce_experiment", "verify_evidence"]

# Artefacts excluded from byte-comparison during reproduction. The manifest
# carries wall-clock provenance, which is deliberately not reproducible.
_REPRODUCTION_EXEMPT: frozenset[str] = frozenset({MANIFEST_NAME, "environment.json"})


@dataclass(slots=True)
class VerificationReport:
    """Outcome of verifying one evidence package."""

    experiment_id: str
    directory: Path
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        """Record one check and its outcome."""
        self.checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            self.passed = False
            self.errors.append(f"{name}: {detail}" if detail else name)

    def as_dict(self) -> dict[str, Any]:
        """Serialise the report."""
        return {
            "experiment_id": self.experiment_id,
            "directory": str(self.directory),
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors,
        }


def verify_evidence(directory: Path) -> VerificationReport:
    """Verify the structural and cryptographic integrity of an evidence package.

    Args:
        directory: The experiment's evidence directory.

    Returns:
        A report; ``passed`` is false if any check failed.
    """
    report = VerificationReport(experiment_id=directory.name, directory=directory, passed=True)

    if not directory.is_dir():
        report.add("directory exists", False, f"{directory} is not a directory")
        return report
    report.add("directory exists", True)

    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        report.add("manifest present", False, f"{MANIFEST_NAME} is missing")
        return report
    report.add("manifest present", True)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add("manifest parses", False, str(exc))
        return report
    report.add("manifest parses", True)
    try:
        ManifestDocument.model_validate(manifest)
    except ValidationError as exc:
        report.add("manifest schema valid", False, str(exc))
        return report
    report.add("manifest schema valid", True)
    report.experiment_id = manifest.get("experiment_id", directory.name)

    if report.experiment_id != directory.name:
        report.add(
            "manifest id matches directory",
            False,
            f"manifest says {report.experiment_id!r}, directory is {directory.name!r}",
        )
    else:
        report.add("manifest id matches directory", True)

    present = {p.name for p in directory.iterdir() if p.is_file()}
    expected = set(ARTIFACT_NAMES) | {MANIFEST_NAME}

    missing = sorted(expected - present)
    report.add(
        "all expected artefacts present",
        not missing,
        f"missing: {', '.join(missing)}" if missing else "",
    )

    unexpected = sorted(present - expected)
    report.add(
        "no unexpected files",
        not unexpected,
        f"unexpected: {', '.join(unexpected)}" if unexpected else "",
    )

    artifacts = manifest.get("artifacts", {})
    for name in ARTIFACT_NAMES:
        path = directory / name
        if not path.is_file():
            continue
        recorded = artifacts.get(name)
        if recorded is None:
            report.add(f"digest recorded for {name}", False, "no entry in manifest")
            continue
        actual = _sha256_file(path)
        if actual != recorded.get("sha256"):
            report.add(
                f"digest matches for {name}",
                False,
                f"expected {recorded.get('sha256')}, computed {actual}",
            )
        else:
            report.add(f"digest matches for {name}", True)

    recorded_digest = manifest.get("integrity", {}).get("digest")
    if artifacts:
        computed = integrity_digest(artifacts)
        report.add(
            "integrity digest matches",
            computed == recorded_digest,
            "" if computed == recorded_digest else f"expected {recorded_digest}, got {computed}",
        )

    _validate_structured_artifacts(directory, report)

    return report


def _validate_structured_artifacts(directory: Path, report: VerificationReport) -> None:
    """Validate schemas and cross-artifact experiment identity."""
    experiment_id = report.experiment_id
    documents: dict[str, dict[str, Any]] = {}
    for name in (
        "configuration.json",
        "environment.json",
        "scenario.json",
        "invariants.json",
        "consequences.json",
        "metrics.json",
        "graph.json",
        "verification.json",
    ):
        path = directory / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.add(f"{name} parses", False, str(exc))
            continue
        if not isinstance(payload, dict):
            report.add(f"{name} is an object", False, "top-level JSON value is not an object")
            continue
        report.add(f"{name} parses", True)
        documents[name] = payload
        observed_id = payload.get("experiment_id")
        report.add(
            f"{name} experiment id matches",
            observed_id == experiment_id,
            "" if observed_id == experiment_id else f"found {observed_id!r}",
        )

    try:
        EnvironmentDocument.model_validate(documents.get("environment.json", {}))
    except ValidationError as exc:
        report.add("environment schema valid", False, str(exc))
    else:
        report.add("environment schema valid", True)

    try:
        verification = VerificationDocument.model_validate(documents.get("verification.json", {}))
    except ValidationError as exc:
        report.add("verification schema valid", False, str(exc))
    else:
        report.add("verification schema valid", True)
        report.add(
            "independent result verification passed",
            verification.passed,
            "; ".join(verification.errors),
        )

    events_path = directory / "events.jsonl"
    if events_path.is_file():
        event_errors: list[str] = []
        for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = EventEnvelope.model_validate_json(line)
            except ValidationError as exc:
                event_errors.append(f"line {line_number}: {exc}")
                continue
            if event.experiment_id != experiment_id:
                event_errors.append(f"line {line_number}: experiment_id={event.experiment_id!r}")
            if event.timestamp != event.t_s:
                event_errors.append(f"line {line_number}: timestamp and t_s differ")
        report.add(
            "event envelopes valid",
            not event_errors,
            "; ".join(event_errors[:5]),
        )


def reproduce_experiment(directory: Path) -> VerificationReport:
    """Re-execute an experiment from its evidence and compare the artefacts.

    Reads the configuration, scenario, variant and seed recorded in the package,
    runs the experiment again into a temporary directory, and compares every
    artefact byte-for-byte.

    Args:
        directory: The experiment's evidence directory.

    Returns:
        A report; ``passed`` is false if any artefact differs.
    """
    # Imported here to avoid a circular import at module load: metrics depends on
    # the scenario engine, which the evidence package also imports.
    from blackstart.analysis.metrics import compute_metrics

    report = VerificationReport(experiment_id=directory.name, directory=directory, passed=True)

    config_path = directory / "configuration.json"
    if not config_path.is_file():
        report.add("configuration recorded", False, "configuration.json is missing")
        return report
    report.add("configuration recorded", True)

    document = json.loads(config_path.read_text(encoding="utf-8"))
    scenario_path = directory / "scenario.json"
    if not scenario_path.is_file():
        report.add("scenario recorded", False, "scenario.json is missing")
        return report
    scenario_document = json.loads(scenario_path.read_text(encoding="utf-8"))
    report.add("scenario recorded", True)
    try:
        config = BlackstartConfig.model_validate(document["config"])
        scenario = Scenario.model_validate(scenario_document["scenario"])
        variant = resolve_variant(document["variant"]["name"])
        seed = int(document["seed"])
    except (KeyError, ValueError) as exc:
        report.add("configuration is loadable", False, str(exc))
        return report
    report.add("configuration is loadable", True)

    runner = ExperimentRunner(config, scenario, variant, seed_override=seed)
    if runner.experiment_id != directory.name:
        report.add(
            "recomputed experiment id matches",
            False,
            f"recomputed {runner.experiment_id}, package is {directory.name}",
        )
        return report
    report.add("recomputed experiment id matches", True)

    result = runner.run()
    metrics = compute_metrics(result, config)

    temp_root = Path(tempfile.mkdtemp(prefix="blackstart-reproduce-"))
    try:
        fresh = write_evidence(result, config, metrics, temp_root)
        for name in ARTIFACT_NAMES:
            if name in _REPRODUCTION_EXEMPT:
                continue
            original = directory / name
            if not original.is_file():
                report.add(f"reproduces {name}", False, "original artefact missing")
                continue
            same = _sha256_file(original) == _sha256_file(fresh / name)
            report.add(
                f"reproduces {name}",
                same,
                "" if same else "byte-level difference between stored and re-run artefact",
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    return report
