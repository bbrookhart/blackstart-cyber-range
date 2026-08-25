"""Integration tests asserting every scenario's measured outcome.

Each scenario declares an ``expected`` block populated from actual runs. These
tests re-derive those outcomes. A divergence means either the implementation
regressed or the design intent was wrong -- both require investigation, not an
updated number.

Several tests here assert the *specific research claims* the README makes, so
that a claim cannot survive a change that invalidates it.
"""

from __future__ import annotations

from typing import Any

import pytest
from blackstart.analysis.metrics import compute_metrics
from blackstart.core.config import BlackstartConfig
from blackstart.scenario_engine.loader import list_scenarios, load_scenario
from blackstart.scenario_engine.orchestration import ExperimentRunner, resolve_variant

pytestmark = pytest.mark.integration

VARIANTS = ("backstop-disabled", "backstop-enabled")


def run(config: BlackstartConfig, scenario_id: str, variant_name: str):
    """Execute one scenario under one variant and return its metrics."""
    scenario = load_scenario(scenario_id)
    result = ExperimentRunner(config, scenario, resolve_variant(variant_name)).run()
    return result, compute_metrics(result, config)


@pytest.fixture(scope="module")
def measured(config: BlackstartConfig) -> dict[tuple[str, str], dict[str, Any]]:
    """Run every scenario under both variants once, and cache the metrics."""
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for scenario in list_scenarios():
        for variant in VARIANTS:
            _, metrics = run(config, scenario.id, variant)
            results[(scenario.id, variant)] = metrics
    return results


@pytest.mark.parametrize("scenario_id", [s.id for s in list_scenarios()])
@pytest.mark.parametrize("variant", VARIANTS)
class TestDeclaredExpectations:
    def _expectation(self, scenario_id: str, variant: str):
        scenario = load_scenario(scenario_id)
        assert scenario.expected is not None
        return (
            scenario.expected.backstop_disabled
            if variant == "backstop-disabled"
            else scenario.expected.backstop_enabled
        )

    def test_maximum_consequence_matches(self, measured, scenario_id: str, variant: str):
        expectation = self._expectation(scenario_id, variant)
        assert measured[(scenario_id, variant)]["maximum_consequence"] == (
            expectation.maximum_consequence
        )

    def test_violated_invariants_match(self, measured, scenario_id: str, variant: str):
        expectation = self._expectation(scenario_id, variant)
        assert sorted(measured[(scenario_id, variant)]["violated_invariants"]) == sorted(
            expectation.violated_invariants
        )

    def test_service_availability_is_within_the_declared_band(
        self, measured, scenario_id: str, variant: str
    ):
        expectation = self._expectation(scenario_id, variant)
        actual = measured[(scenario_id, variant)]["service_availability_pct"]
        if expectation.service_availability_pct_min is not None:
            assert actual >= expectation.service_availability_pct_min
        if expectation.service_availability_pct_max is not None:
            assert actual <= expectation.service_availability_pct_max


class TestBaselineDiscipline:
    def test_nominal_operation_is_clean_under_both_variants(self, measured):
        """The backstop must be invisible when nothing is wrong."""
        for variant in VARIANTS:
            metrics = measured[("SCN-001", variant)]
            assert metrics["maximum_consequence"] == "C0"
            assert metrics["invariant_violations_total"] == 0

    def test_the_backstop_does_not_disturb_nominal_operation(self, measured):
        """A safety control that changed normal behaviour would be a liability."""
        disabled = measured[("SCN-001", "backstop-disabled")]
        enabled = measured[("SCN-001", "backstop-enabled")]
        assert disabled["max_tank_level_m"] == pytest.approx(enabled["max_tank_level_m"])
        assert disabled["service_availability_pct"] == pytest.approx(
            enabled["service_availability_pct"]
        )


class TestDisturbanceDiscrimination:
    def test_a_benign_surge_degrades_service_without_a_safety_event(self, measured):
        """The discriminating case: a real service consequence, no compromise.

        A range that flagged this as a security event would be producing false
        positives; one that called it harmless would be ignoring a genuine loss
        of service.
        """
        metrics = measured[("SCN-002", "backstop-disabled")]
        assert metrics["maximum_consequence"] == "C2"
        assert metrics["invariant_violations_total"] == 0
        assert metrics["unsafe_state_duration_s"] == 0.0

    def test_the_backstop_is_irrelevant_to_a_physical_disturbance(self, measured):
        """An engineering control on the command path cannot fix a lack of demand
        headroom, and must not appear to."""
        disabled = measured[("SCN-002", "backstop-disabled")]
        enabled = measured[("SCN-002", "backstop-enabled")]
        assert disabled["maximum_consequence"] == enabled["maximum_consequence"]
        assert disabled["service_availability_pct"] == pytest.approx(
            enabled["service_availability_pct"]
        )


class TestFlagshipClaims:
    def test_setpoint_mutation_reaches_an_unsafe_state_without_the_constraint(self, measured):
        metrics = measured[("SCN-004", "backstop-disabled")]
        assert metrics["maximum_consequence"] == "C4"
        assert "INV-001" in metrics["violated_invariants"]
        assert metrics["unsafe_state_duration_s"] > 500.0

    def test_the_constraint_prevents_the_unsafe_state(self, measured):
        metrics = measured[("SCN-004", "backstop-enabled")]
        assert metrics["maximum_consequence"] == "C1"
        assert "INV-001" not in metrics["violated_invariants"]
        assert metrics["unsafe_state_duration_s"] == 0.0

    def test_the_constraint_holds_the_level_below_the_safety_limit(
        self, measured, config: BlackstartConfig
    ):
        limit = config.invariants.by_id("INV-001").limit_m
        assert limit is not None
        assert measured[("SCN-004", "backstop-enabled")]["max_tank_level_m"] < limit

    def test_the_setpoint_clamp_is_what_acts(self, measured):
        """SCN-004 must be stopped by BS-01, not by the high-level trip.

        If the trip were doing the work, the scenario would not demonstrate that
        constraining the command is sufficient -- it would only demonstrate that
        a last-resort interlock catches the result.
        """
        counts = measured[("SCN-004", "backstop-enabled")]["backstop"]["activation_counts"]
        assert counts["BS-01"] > 0
        assert counts["BS-03"] == 0

    def test_the_anomalous_command_is_detectable_in_both_variants(self, measured):
        """INV-004 observes the requested setpoint, so the evidence that an
        implausible command was issued survives the constraint refusing it."""
        for variant in VARIANTS:
            assert "INV-004" in measured[("SCN-004", variant)]["violated_invariants"]


class TestTelemetryIntegrityClaims:
    def test_falsified_telemetry_drives_the_process_unsafe_without_the_constraint(self, measured):
        metrics = measured[("SCN-003", "backstop-disabled")]
        assert metrics["maximum_consequence"] == "C4"
        assert "INV-001" in metrics["violated_invariants"]
        assert metrics["spill_volume_m3"] > 0.0

    def test_the_independent_channel_keeps_the_process_safe(self, measured):
        metrics = measured[("SCN-003", "backstop-enabled")]
        assert metrics["maximum_consequence"] == "C1"
        assert "INV-001" not in metrics["violated_invariants"]

    def test_the_high_level_trip_is_what_acts(self, measured):
        """SCN-003 must be stopped by BS-03, not BS-01: the setpoint is
        legitimate here, and only the independent measurement can help."""
        counts = measured[("SCN-003", "backstop-enabled")]["backstop"]["activation_counts"]
        assert counts["BS-03"] > 0
        assert counts["BS-01"] == 0

    def test_the_operator_remains_deceived_in_both_variants(self, measured):
        """The constraint preserves the process. It does not restore trust in
        telemetry, and the results must not suggest otherwise.
        """
        for variant in VARIANTS:
            assert "INV-005" in measured[("SCN-003", variant)]["violated_invariants"]


class TestVisibilityClaims:
    def test_loss_of_view_is_not_loss_of_control(self, measured):
        metrics = measured[("SCN-005", "backstop-disabled")]
        assert metrics["maximum_consequence"] == "C0"
        assert metrics["invariant_violations_total"] == 0
        assert metrics["service_availability_pct"] == pytest.approx(100.0)

    def test_supervisory_availability_is_measured_separately(self, measured):
        """Conflating visibility with service is a common way to overstate the
        impact of a blackout."""
        metrics = measured[("SCN-005", "backstop-disabled")]
        assert metrics["supervisory_availability_pct"] < 60.0
        assert metrics["service_availability_pct"] == pytest.approx(100.0)


class TestEngineeringTradeoff:
    def test_the_interlock_prevents_equipment_damage(self, measured):
        disabled = measured[("SCN-006", "backstop-disabled")]
        enabled = measured[("SCN-006", "backstop-enabled")]
        assert "INV-003" in disabled["violated_invariants"]
        assert "INV-003" not in enabled["violated_invariants"]

    def test_the_interlock_does_not_prevent_the_service_consequence(self, measured):
        """The honest half of the result: the underlying problem is that there is
        no supply, and no command-path control can create water."""
        enabled = measured[("SCN-006", "backstop-enabled")]
        assert "INV-002" in enabled["violated_invariants"]
        assert enabled["maximum_consequence"] == "C3"

    def test_the_interlock_still_improves_the_outcome(self, measured):
        disabled = measured[("SCN-006", "backstop-disabled")]
        enabled = measured[("SCN-006", "backstop-enabled")]
        assert disabled["maximum_consequence"] == "C5"
        assert enabled["maximum_consequence"] == "C3"
        assert enabled["service_availability_pct"] > disabled["service_availability_pct"]
