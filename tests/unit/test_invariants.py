"""Unit tests for the safety and mission invariants.

Each invariant is driven directly, including the temporal behaviour that the
tolerance windows exist to express. Tests deliberately enter unsafe simulated
states -- that is the point of an invariant test.
"""

from __future__ import annotations

import pytest
from blackstart.core.config import BlackstartConfig
from blackstart.core.invariants.engine import InvariantEngine, build_invariants
from blackstart.core.invariants.water import (
    CommandRateInvariant,
    DryRunInvariant,
    MaximumLevelInvariant,
    MinimumReserveInvariant,
    SetpointBoundInvariant,
    TelemetryIntegrityInvariant,
)
from blackstart.core.models import InvariantStatus

from tests.conftest import make_state

pytestmark = pytest.mark.unit

DT = 0.5


class TestMaximumLevel:
    def test_ok_well_below_the_limit(self, config: BlackstartConfig):
        inv = MaximumLevelInvariant(config.invariants.by_id("INV-001"))
        sample = inv.evaluate(make_state(tank_level_m=3.0), DT)
        assert sample.status is InvariantStatus.OK

    def test_approaching_inside_the_margin(self, config: BlackstartConfig):
        # limit 4.50, margin 0.25 -> APPROACHING at or above 4.25
        inv = MaximumLevelInvariant(config.invariants.by_id("INV-001"))
        assert inv.evaluate(make_state(tank_level_m=4.30), DT).status is (
            InvariantStatus.APPROACHING
        )

    def test_violated_immediately_above_the_limit(self, config: BlackstartConfig):
        """No tolerance period: exceeding a structural safe level is instantaneous."""
        inv = MaximumLevelInvariant(config.invariants.by_id("INV-001"))
        assert inv.evaluate(make_state(tank_level_m=4.51), DT).status is (InvariantStatus.VIOLATED)

    def test_records_duration_and_peak_excursion(self, config: BlackstartConfig):
        inv = MaximumLevelInvariant(config.invariants.by_id("INV-001"))
        for step, level in enumerate([4.6, 4.9, 4.7]):
            inv.evaluate(make_state(t_s=step * DT, tank_level_m=level), DT)
        outcome = inv.finalise(3 * DT)
        assert outcome.violated
        assert outcome.violation_count == 1
        assert outcome.total_violation_s == pytest.approx(1.5)
        assert outcome.peak_excursion == pytest.approx(0.40)  # 4.90 - 4.50

    def test_separate_excursions_are_separate_intervals(self, config: BlackstartConfig):
        inv = MaximumLevelInvariant(config.invariants.by_id("INV-001"))
        for step, level in enumerate([4.6, 3.0, 4.6]):
            inv.evaluate(make_state(t_s=step * DT, tank_level_m=level), DT)
        outcome = inv.finalise(3 * DT)
        assert outcome.violation_count == 2


class TestMinimumReserve:
    def test_brief_excursion_is_not_a_violation(self, config: BlackstartConfig):
        """Below reserve during a surge is normal; sustained loss is not."""
        inv = MinimumReserveInvariant(config.invariants.by_id("INV-002"))
        for step in range(20):  # 10 s, far inside the 120 s tolerance
            sample = inv.evaluate(make_state(t_s=step * DT, tank_level_m=0.5), DT)
        assert sample.status is InvariantStatus.APPROACHING
        assert not inv.finalise(20 * DT).violated

    def test_violated_once_the_tolerance_elapses(self, config: BlackstartConfig):
        inv = MinimumReserveInvariant(config.invariants.by_id("INV-002"))
        tolerance = config.invariants.by_id("INV-002").tolerance_s
        for step in range(int(tolerance / DT) + 2):
            sample = inv.evaluate(make_state(t_s=step * DT, tank_level_m=0.5), DT)
        assert sample.status is InvariantStatus.VIOLATED

    def test_recovery_resets_the_tolerance_window(self, config: BlackstartConfig):
        inv = MinimumReserveInvariant(config.invariants.by_id("INV-002"))
        for step in range(200):
            inv.evaluate(make_state(t_s=step * DT, tank_level_m=0.5), DT)
        inv.evaluate(make_state(t_s=100.0, tank_level_m=3.0), DT)
        sample = inv.evaluate(make_state(t_s=100.5, tank_level_m=0.5), DT)
        assert sample.status is InvariantStatus.APPROACHING

    def test_peak_tracks_downward_for_a_lower_bound(self, config: BlackstartConfig):
        inv = MinimumReserveInvariant(config.invariants.by_id("INV-002"))
        for step in range(300):
            level = 0.9 if step < 280 else 0.2
            inv.evaluate(make_state(t_s=step * DT, tank_level_m=level), DT)
        outcome = inv.finalise(300 * DT)
        assert outcome.violated
        assert outcome.intervals[0].peak_value == pytest.approx(0.2)


class TestDryRun:
    def test_ok_when_pump_is_off_regardless_of_source(self, config: BlackstartConfig):
        inv = DryRunInvariant(config.invariants.by_id("INV-003"), config.process)
        sample = inv.evaluate(make_state(pump_energised=False, source_level_m=0.0), DT)
        assert sample.status is InvariantStatus.OK

    def test_ok_when_pump_runs_with_suction(self, config: BlackstartConfig):
        inv = DryRunInvariant(config.invariants.by_id("INV-003"), config.process)
        sample = inv.evaluate(make_state(pump_energised=True, source_level_m=6.0), DT)
        assert sample.status is InvariantStatus.OK

    def test_approaching_when_source_runs_low_while_pumping(self, config: BlackstartConfig):
        inv = DryRunInvariant(config.invariants.by_id("INV-003"), config.process)
        limit = config.process.source.suction_limit_m
        sample = inv.evaluate(make_state(pump_energised=True, source_level_m=limit + 0.1), DT)
        assert sample.status is InvariantStatus.APPROACHING

    def test_violated_after_the_reaction_tolerance(self, config: BlackstartConfig):
        inv = DryRunInvariant(config.invariants.by_id("INV-003"), config.process)
        tolerance = config.invariants.by_id("INV-003").tolerance_s
        for step in range(int(tolerance / DT) + 1):
            sample = inv.evaluate(
                make_state(t_s=step * DT, pump_energised=True, source_level_m=0.1), DT
            )
        assert sample.status is InvariantStatus.VIOLATED


class TestCommandRate:
    def test_step_change_in_setpoint_breaches_the_slew_limit(self, config: BlackstartConfig):
        inv = CommandRateInvariant(config.invariants.by_id("INV-004"))
        inv.evaluate(make_state(t_s=0.0, requested_setpoint_m=3.20), DT)
        sample = inv.evaluate(make_state(t_s=DT, requested_setpoint_m=4.80), DT)
        assert sample.status is InvariantStatus.VIOLATED
        assert sample.detail["slew_breach"] == 1.0

    def test_observes_requested_not_effective_setpoint(self, config: BlackstartConfig):
        """The detection signal must survive the backstop refusing the command.

        A command-rate anomaly is evidence that an implausible command was
        *issued*. That fact does not change because a downstream constraint then
        rejected it, so the invariant must not read the constrained value.
        """
        inv = CommandRateInvariant(config.invariants.by_id("INV-004"))
        inv.evaluate(make_state(t_s=0.0, requested_setpoint_m=3.20, effective_setpoint_m=3.20), DT)
        sample = inv.evaluate(
            make_state(t_s=DT, requested_setpoint_m=4.80, effective_setpoint_m=3.205), DT
        )
        assert sample.status is InvariantStatus.VIOLATED

    def test_gradual_setpoint_movement_is_permitted(self, config: BlackstartConfig):
        inv = CommandRateInvariant(config.invariants.by_id("INV-004"))
        setpoint = 3.20
        for step in range(20):
            setpoint += 0.02  # 0.04 m/s, inside the 0.05 m/s limit
            sample = inv.evaluate(make_state(t_s=step * DT, requested_setpoint_m=setpoint), DT)
        assert sample.status is not InvariantStatus.VIOLATED

    def test_start_rate_uses_a_minimum_observation_window(self, config: BlackstartConfig):
        """One start at t=0 must not imply an unbounded starts-per-hour figure."""
        inv = CommandRateInvariant(config.invariants.by_id("INV-004"))
        sample = inv.evaluate(make_state(t_s=0.5, pump_starts=1), DT)
        assert sample.detail["starts_per_hour"] == pytest.approx(6.0)
        assert sample.detail["rate_breach"] == 0.0

    def test_short_cycling_breaches_the_start_rate(self, config: BlackstartConfig):
        inv = CommandRateInvariant(config.invariants.by_id("INV-004"))
        starts = 0
        sample = None
        for step in range(400):
            t_s = step * DT
            if step % 20 == 0:
                starts += 1
            sample = inv.evaluate(make_state(t_s=t_s, pump_starts=starts), DT)
        assert sample is not None
        assert sample.detail["rate_breach"] == 1.0


class TestSetpointBound:
    def test_accepts_boundary_values(self, config: BlackstartConfig):
        inv = SetpointBoundInvariant(config.invariants.by_id("INV-005"))
        sample = inv.evaluate(make_state(effective_setpoint_m=3.60), DT)
        assert sample.status is InvariantStatus.OK

    def test_rejects_an_effective_target_above_the_envelope(self, config: BlackstartConfig):
        inv = SetpointBoundInvariant(config.invariants.by_id("INV-005"))
        sample = inv.evaluate(make_state(requested_setpoint_m=4.80, effective_setpoint_m=4.80), DT)
        assert sample.status is InvariantStatus.VIOLATED
        assert sample.detail["requested_setpoint_m"] == pytest.approx(4.80)

    def test_recovers_when_the_effective_target_is_constrained(self, config: BlackstartConfig):
        inv = SetpointBoundInvariant(config.invariants.by_id("INV-005"))
        inv.evaluate(make_state(effective_setpoint_m=4.80), DT)
        sample = inv.evaluate(make_state(effective_setpoint_m=3.60), DT)
        assert sample.status is InvariantStatus.OK
        assert inv.finalise(2 * DT).violation_count == 1


class TestTelemetryIntegrity:
    def test_ok_within_transmitter_noise(self, config: BlackstartConfig):
        inv = TelemetryIntegrityInvariant(config.invariants.by_id("INV-006"))
        sample = inv.evaluate(make_state(tank_level_m=3.20, reported_level_m=3.205), DT)
        assert sample.status is InvariantStatus.OK

    def test_violated_by_a_sustained_divergence(self, config: BlackstartConfig):
        inv = TelemetryIntegrityInvariant(config.invariants.by_id("INV-006"))
        tolerance = config.invariants.by_id("INV-006").tolerance_s
        for step in range(int(tolerance / DT) + 1):
            sample = inv.evaluate(
                make_state(t_s=step * DT, tank_level_m=4.0, reported_level_m=2.5), DT
            )
        assert sample.status is InvariantStatus.VIOLATED

    def test_evaluates_truth_against_report_not_report_alone(self, config: BlackstartConfig):
        """The evidence model must not be falsifiable by the same effect that
        falsifies the operator view."""
        inv = TelemetryIntegrityInvariant(config.invariants.by_id("INV-006"))
        sample = inv.evaluate(make_state(tank_level_m=4.9, reported_level_m=3.2), DT)
        assert sample.detail["true_level_m"] == pytest.approx(4.9)
        assert sample.detail["reported_level_m"] == pytest.approx(3.2)
        assert sample.value == pytest.approx(1.7)


class TestEngine:
    def test_builds_every_configured_invariant(self, config: BlackstartConfig):
        built = build_invariants(config.invariants, config.process)
        assert [inv.invariant_id for inv in built] == [
            spec.id for spec in config.invariants.invariants
        ]

    def test_rejects_an_invariant_with_no_implementation(self, config: BlackstartConfig):
        """Safety logic must be implemented in code, never inferred by name."""
        spec = config.invariants.by_id("INV-001").model_copy(update={"id": "INV-999"})
        broken = config.invariants.model_copy(update={"invariants": [spec]})
        with pytest.raises(ValueError, match="no implementation registered"):
            build_invariants(broken, config.process)

    def test_reports_violated_ids_for_the_step(self, config: BlackstartConfig):
        engine = InvariantEngine(config.invariants, config.process)
        result = engine.evaluate(make_state(tank_level_m=4.9), DT)
        assert "INV-001" in result.violated_ids
        assert result.violated_count == 1

    def test_summary_lists_violations(self, config: BlackstartConfig):
        engine = InvariantEngine(config.invariants, config.process)
        engine.evaluate(make_state(tank_level_m=4.9), DT)
        summary = engine.summary(DT)
        assert summary["violated_invariants"] == ["INV-001"]
        assert summary["total_violations"] == 1
