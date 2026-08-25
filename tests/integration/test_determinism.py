"""Integration tests for the determinism contract (ADR-005).

An experiment is a pure function of ``(version, configuration, seed)``. If that
stops being true, every published result silently becomes unverifiable, so it is
tested directly rather than assumed.
"""

from __future__ import annotations

import pytest
from blackstart.analysis.metrics import compute_metrics
from blackstart.core.config import BlackstartConfig, canonical_json
from blackstart.evidence.package import write_evidence
from blackstart.scenario_engine.loader import load_scenario
from blackstart.scenario_engine.orchestration import ExperimentRunner, resolve_variant

pytestmark = pytest.mark.integration

SCENARIO_ID = "SCN-004"


@pytest.fixture(scope="module")
def scenario():
    """The flagship scenario, shortened so repeated runs stay cheap."""
    return load_scenario(SCENARIO_ID).model_copy(update={"duration_s": 400.0})


class TestRepeatability:
    def test_two_runs_produce_identical_traces(self, config: BlackstartConfig, scenario):
        variant = resolve_variant("backstop-disabled")
        first = ExperimentRunner(config, scenario, variant).run()
        second = ExperimentRunner(config, scenario, variant).run()
        assert first.trace.rows == second.trace.rows

    def test_two_runs_produce_identical_event_streams(self, config: BlackstartConfig, scenario):
        variant = resolve_variant("backstop-enabled")
        first = ExperimentRunner(config, scenario, variant).run()
        second = ExperimentRunner(config, scenario, variant).run()
        assert [e.as_dict() for e in first.events.events] == [
            e.as_dict() for e in second.events.events
        ]

    def test_two_runs_produce_identical_metrics(self, config: BlackstartConfig, scenario):
        variant = resolve_variant("backstop-enabled")
        first = ExperimentRunner(config, scenario, variant).run()
        second = ExperimentRunner(config, scenario, variant).run()
        assert compute_metrics(first, config) == compute_metrics(second, config)

    def test_two_runs_produce_identical_evidence_bytes(
        self, config: BlackstartConfig, scenario, tmp_path
    ):
        variant = resolve_variant("backstop-enabled")
        digests = []
        for index in range(2):
            result = ExperimentRunner(config, scenario, variant).run()
            metrics = compute_metrics(result, config)
            directory = write_evidence(result, config, metrics, tmp_path / str(index))
            digests.append(
                {
                    path.name: path.read_bytes()
                    for path in sorted(directory.iterdir())
                    if path.name != "manifest.json"
                }
            )
        assert digests[0] == digests[1]


class TestExperimentIdentity:
    def test_identifier_is_deterministic(self, config: BlackstartConfig, scenario):
        variant = resolve_variant("backstop-disabled")
        first = ExperimentRunner(config, scenario, variant)
        second = ExperimentRunner(config, scenario, variant)
        assert first.experiment_id == second.experiment_id

    def test_variants_get_distinct_identifiers(self, config: BlackstartConfig, scenario):
        disabled = ExperimentRunner(config, scenario, resolve_variant("backstop-disabled"))
        enabled = ExperimentRunner(config, scenario, resolve_variant("backstop-enabled"))
        assert disabled.experiment_id != enabled.experiment_id

    def test_seed_change_changes_the_identifier(self, config: BlackstartConfig, scenario):
        variant = resolve_variant("backstop-enabled")
        base = ExperimentRunner(config, scenario, variant)
        other = ExperimentRunner(config, scenario, variant, seed_override=999)
        assert base.experiment_id != other.experiment_id

    def test_identifier_names_its_scenario_and_variant(self, config: BlackstartConfig, scenario):
        """A reviewer should be able to read a directory name."""
        runner = ExperimentRunner(config, scenario, resolve_variant("backstop-enabled"))
        assert "SCN004" in runner.experiment_id
        assert "backstop-enabled" in runner.experiment_id

    def test_prose_edits_do_not_change_the_identifier(self, config: BlackstartConfig, scenario):
        """Recording a measured expectation, or fixing a typo in a description,
        must not silently invalidate an experiment identifier."""
        variant = resolve_variant("backstop-enabled")
        edited = scenario.model_copy(
            update={
                "name": "Renamed scenario",
                "description": "Completely rewritten description.",
                "notes": "different notes",
                "expected": None,
            }
        )
        assert (
            ExperimentRunner(config, scenario, variant).experiment_id
            == ExperimentRunner(config, edited, variant).experiment_id
        )

    def test_a_changed_effect_parameter_changes_the_identifier(
        self, config: BlackstartConfig, scenario
    ):
        variant = resolve_variant("backstop-enabled")
        events = [scenario.events[0].model_copy(update={"params": {"value_m": 4.90}})]
        edited = scenario.model_copy(update={"events": events})
        assert (
            ExperimentRunner(config, scenario, variant).experiment_id
            != ExperimentRunner(config, edited, variant).experiment_id
        )


class TestSeedSensitivity:
    def test_different_seeds_change_the_detail_but_not_the_finding(self, config: BlackstartConfig):
        """The flagship result must not be an artefact of one lucky seed.

        Instrument noise and demand variation differ across seeds, so the traces
        differ. The conclusion -- unsafe without the constraint, safe with it --
        must not.

        Uses the scenario's full duration deliberately. The excursion needs
        roughly six minutes to develop after the setpoint is mutated, so a
        shortened run would end before the effect appears and would pass this
        test for the wrong reason.
        """
        scenario = load_scenario(SCENARIO_ID)
        for seed in (1, 7, 12345, 98765):
            disabled = ExperimentRunner(
                config, scenario, resolve_variant("backstop-disabled"), seed_override=seed
            ).run()
            enabled = ExperimentRunner(
                config, scenario, resolve_variant("backstop-enabled"), seed_override=seed
            ).run()

            assert "INV-001" in disabled.violated_invariants, f"seed {seed}"
            assert "INV-001" not in enabled.violated_invariants, f"seed {seed}"
            assert disabled.maximum_consequence > enabled.maximum_consequence, f"seed {seed}"


class TestCanonicalSerialisation:
    def test_key_order_does_not_affect_output(self):
        assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})

    def test_output_has_no_incidental_whitespace(self):
        assert canonical_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'
