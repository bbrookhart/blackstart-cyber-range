"""Integration tests for the full pipeline.

scenario -> controller -> physics -> telemetry -> evidence -> metrics
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from blackstart.analysis.compare import VariantRun, compare_variants
from blackstart.analysis.metrics import NOT_IMPLEMENTED, compute_metrics
from blackstart.core.config import BlackstartConfig
from blackstart.evidence.package import ARTIFACT_NAMES, MANIFEST_NAME, write_evidence
from blackstart.evidence.verify import reproduce_experiment, verify_evidence
from blackstart.scenario_engine.loader import load_scenario
from blackstart.scenario_engine.orchestration import ExperimentRunner, resolve_variant

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def baseline(config: BlackstartConfig, tmp_path_factory: pytest.TempPathFactory):
    """Run SCN-001 once and write its evidence package."""
    scenario = load_scenario("SCN-001")
    variant = resolve_variant("backstop-enabled")
    result = ExperimentRunner(config, scenario, variant).run()
    metrics = compute_metrics(result, config)
    root = tmp_path_factory.mktemp("evidence")
    directory = write_evidence(result, config, metrics, root)
    return result, metrics, directory


class TestPipeline:
    def test_produces_every_expected_artefact(self, baseline):
        _, _, directory = baseline
        for name in (*ARTIFACT_NAMES, MANIFEST_NAME):
            assert (directory / name).is_file(), f"{name} missing"

    def test_process_trace_covers_the_whole_experiment(self, baseline):
        result, _, directory = baseline
        with (directory / "process.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == result.step_count
        assert float(rows[0]["t_s"]) == 0.0
        assert float(rows[-1]["t_s"]) == pytest.approx(result.duration_s - result.timestep_s)

    def test_trace_records_both_views_of_the_process(self, baseline):
        _, _, directory = baseline
        with (directory / "process.csv").open(encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        assert "true_tank_level_m" in header
        assert "reported_tank_level_m" in header
        assert "independent_level_m" in header

    def test_event_stream_is_ordered_and_well_formed(self, baseline):
        result, _, directory = baseline
        lines = (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines]
        assert events, "no events emitted"
        assert [e["t_s"] for e in events] == sorted(e["t_s"] for e in events)
        for event in events:
            assert event["experiment_id"] == result.experiment_id
            assert {"zone", "event_type", "severity", "asset_id", "data"} <= set(event)

    def test_event_stream_brackets_the_experiment(self, baseline):
        _, _, directory = baseline
        events = [
            json.loads(line)
            for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        lifecycle = [e for e in events if e["event_type"] == "experiment.lifecycle"]
        assert [e["data"]["phase"] for e in lifecycle] == ["start", "end"]

    def test_summary_is_human_readable(self, baseline):
        result, _, directory = baseline
        summary = (directory / "summary.md").read_text(encoding="utf-8")
        assert result.experiment_id in summary
        assert result.scenario.research_question.strip()[:40] in summary
        assert "Limitations" in summary


class TestMetrics:
    def test_baseline_is_clean(self, baseline):
        """Without a clean baseline no other result is interpretable."""
        _, metrics, _ = baseline
        assert metrics["maximum_consequence"] == "C0"
        assert metrics["invariant_violations_total"] == 0
        assert metrics["service_availability_pct"] == pytest.approx(100.0)
        assert metrics["unsafe_state_duration_s"] == 0.0
        assert metrics["spill_volume_m3"] == 0.0

    def test_baseline_stays_inside_the_safe_envelope(self, baseline, config: BlackstartConfig):
        _, metrics, _ = baseline
        upper = config.invariants.by_id("INV-001").limit_m
        lower = config.invariants.by_id("INV-002").limit_m
        assert upper is not None and lower is not None
        assert metrics["max_tank_level_m"] < upper
        assert metrics["min_tank_level_m"] > lower

    def test_unmeasurable_metrics_are_marked_not_implemented(self, baseline):
        """Reporting a detection latency of 0.0 would be a fabrication."""
        _, metrics, _ = baseline
        for key in ("detection_latency_s", "containment_latency_s", "false_positive_rate"):
            assert metrics[key] == NOT_IMPLEMENTED

    def test_recovery_is_reported_as_not_applicable_without_a_disturbance(self, baseline):
        _, metrics, _ = baseline
        assert metrics["recovery"]["status"] == "no_disturbance"

    def test_metrics_refuse_an_empty_trace(self, baseline, config: BlackstartConfig):
        result, _, _ = baseline
        empty = result.trace.__class__()
        stripped = result
        original, stripped.trace = stripped.trace, empty
        try:
            with pytest.raises(ValueError, match="empty trace"):
                compute_metrics(stripped, config)
        finally:
            stripped.trace = original


class TestEvidenceIntegrity:
    def test_package_verifies(self, baseline):
        _, _, directory = baseline
        report = verify_evidence(directory)
        assert report.passed, report.errors

    def test_verification_detects_a_modified_artefact(self, baseline, tmp_path: Path):
        import shutil

        _, _, directory = baseline
        copy = tmp_path / directory.name
        shutil.copytree(directory, copy)
        target = copy / "process.csv"
        target.write_text(target.read_text(encoding="utf-8") + "0,0,0\n", encoding="utf-8")

        report = verify_evidence(copy)
        assert not report.passed
        assert any("process.csv" in error for error in report.errors)

    def test_verification_detects_an_unexpected_file(self, baseline, tmp_path: Path):
        import shutil

        _, _, directory = baseline
        copy = tmp_path / f"{directory.name}-extra"
        shutil.copytree(directory, copy)
        (copy / "notes.txt").write_text("stray", encoding="utf-8")

        report = verify_evidence(copy)
        assert not report.passed
        assert any("unexpected" in error for error in report.errors)

    def test_verification_detects_a_missing_file(self, baseline, tmp_path: Path):
        import shutil

        _, _, directory = baseline
        copy = tmp_path / f"{directory.name}-missing"
        shutil.copytree(directory, copy)
        (copy / "metrics.json").unlink()

        report = verify_evidence(copy)
        assert not report.passed

    def test_missing_directory_fails_cleanly(self, tmp_path: Path):
        report = verify_evidence(tmp_path / "EXP-does-not-exist")
        assert not report.passed


class TestReproduction:
    def test_experiment_reproduces_byte_for_byte(self, baseline):
        """The strongest reproducibility claim v0.1 makes (ADR-005)."""
        _, _, directory = baseline
        report = reproduce_experiment(directory)
        assert report.passed, report.errors

    def test_reproduction_covers_every_artefact_except_the_manifest(self, baseline):
        _, _, directory = baseline
        report = reproduce_experiment(directory)
        reproduced = {
            check["check"].removeprefix("reproduces ")
            for check in report.checks
            if check["check"].startswith("reproduces ")
        }
        assert reproduced == set(ARTIFACT_NAMES) - {MANIFEST_NAME}

    def test_manifest_provenance_is_excluded_from_the_hash(self, baseline):
        """Wall-clock provenance must not break byte-level reproducibility."""
        _, _, directory = baseline
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        assert "generated_at" in manifest["provenance"]
        assert "provenance" not in manifest["artifacts"]
        assert "provenance excluded" in manifest["integrity"]["scope"]


class TestExperimentIsolation:
    def test_invariant_state_does_not_leak_between_experiments(self, config: BlackstartConfig):
        """A leaked stateful invariant would silently corrupt later results."""
        scenario = load_scenario("SCN-004")
        variant = resolve_variant("backstop-disabled")

        first = ExperimentRunner(config, scenario, variant).run()
        second = ExperimentRunner(config, scenario, variant).run()

        assert first.invariants == second.invariants
        assert first.consequences.as_dict() == second.consequences.as_dict()

    def test_scenario_parameters_are_not_polluted_across_runs(self, config: BlackstartConfig):
        """`experiment compare` runs one scenario twice in one process."""
        scenario = load_scenario("SCN-004")
        before = scenario.events[0].params.copy()

        ExperimentRunner(config, scenario, resolve_variant("backstop-disabled")).run()
        ExperimentRunner(config, scenario, resolve_variant("backstop-enabled")).run()

        assert scenario.events[0].params == before


class TestComparison:
    def test_flagship_comparison_shows_the_engineered_difference(self, config: BlackstartConfig):
        scenario = load_scenario("SCN-004")
        runs = []
        for name in ("backstop-disabled", "backstop-enabled"):
            result = ExperimentRunner(config, scenario, resolve_variant(name)).run()
            runs.append(VariantRun(result=result, metrics=compute_metrics(result, config)))

        report = compare_variants(runs)
        consequence_row = next(row for row in report.rows if row["metric"] == "maximum_consequence")
        assert consequence_row["delta"]["improved"] is True
        assert "SCN-004" in report.render()

    def test_comparison_requires_a_shared_scenario_and_seed(self, config: BlackstartConfig):
        """Comparing across different inputs would not isolate the variable."""
        variant = resolve_variant("backstop-enabled")
        first = ExperimentRunner(config, load_scenario("SCN-001"), variant).run()
        second = ExperimentRunner(config, load_scenario("SCN-002"), variant).run()
        runs = [
            VariantRun(result=first, metrics=compute_metrics(first, config)),
            VariantRun(result=second, metrics=compute_metrics(second, config)),
        ]
        with pytest.raises(ValueError, match="one scenario and one seed"):
            compare_variants(runs)

    def test_comparison_requires_at_least_two_runs(self, config: BlackstartConfig):
        result = ExperimentRunner(
            config, load_scenario("SCN-001"), resolve_variant("backstop-enabled")
        ).run()
        runs = [VariantRun(result=result, metrics=compute_metrics(result, config))]
        with pytest.raises(ValueError, match="at least two"):
            compare_variants(runs)
