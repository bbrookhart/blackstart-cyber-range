"""Unit tests for control logic, the PLC scan abstraction, and the backstop.

The backstop tests matter most: this is the component the flagship result
attributes its difference to, so each rule is driven directly rather than only
through a scenario.
"""

from __future__ import annotations

import pytest
from blackstart.controller.backstop import EngineeringBackstop
from blackstart.controller.control_logic import ControlRequest, LevelController
from blackstart.controller.plc_sim import PlcScanner
from blackstart.core.config import BlackstartConfig
from blackstart.core.models import ReportedState

from tests.import_analysis import imported_modules, python_sources

pytestmark = pytest.mark.unit

DT = 0.5


def reported(level_m: float) -> ReportedState:
    """A healthy reported state at the given level."""
    return ReportedState(
        tank_level_m=level_m,
        inflow_m3_s=0.0,
        outflow_m3_s=0.035,
        pump_energised=False,
        valve_position=1.0,
    )


class TestLevelController:
    def test_starts_the_pump_at_the_lower_band_edge(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        request = controller.scan(reported(2.79), 3.20, t_s=100.0)
        assert request.pump_run is True
        assert controller.pump_starts == 1

    def test_stops_the_pump_at_the_upper_band_edge(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        controller.scan(reported(2.70), 3.20, t_s=100.0)
        request = controller.scan(reported(3.65), 3.20, t_s=200.0)
        assert request.pump_run is False

    def test_holds_inside_the_deadband(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        request = controller.scan(reported(3.20), 3.20, t_s=100.0)
        assert request.pump_run is False
        assert controller.pump_starts == 0

    def test_honours_minimum_run_time(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        controller.scan(reported(2.70), 3.20, t_s=100.0)
        request = controller.scan(reported(3.90), 3.20, t_s=105.0)
        assert request.pump_run is True  # min_run_time_s is 20 s

    def test_honours_minimum_off_time(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        controller.scan(reported(2.70), 3.20, t_s=100.0)
        controller.scan(reported(3.90), 3.20, t_s=130.0)
        request = controller.scan(reported(2.70), 3.20, t_s=140.0)
        assert request.pump_run is False  # min_off_time_s is 30 s

    def test_acts_on_reported_level_not_ground_truth(self, config: BlackstartConfig):
        """A controller immune to falsified telemetry would make SCN-003 vacuous."""
        controller = LevelController(config.process)
        request = controller.scan(reported(2.50), 3.20, t_s=100.0)
        assert request.pump_run is True

    def test_setpoint_moves_the_band(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        assert controller.scan(reported(3.90), 4.80, t_s=100.0).pump_run is True

    def test_reserve_protection_throttles_the_outlet(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        engage = config.process.control.reserve_protection.engage_level_m
        request = controller.scan(reported(engage - 0.01), 3.20, t_s=100.0)
        assert request.reserve_protection_active is True
        assert request.valve_position == pytest.approx(
            config.process.control.reserve_protection.throttled_position
        )

    def test_reserve_protection_has_hysteresis(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        protection = config.process.control.reserve_protection
        controller.scan(reported(protection.engage_level_m - 0.01), 3.20, t_s=100.0)
        held = controller.scan(reported(protection.release_level_m - 0.05), 3.20, t_s=200.0)
        assert held.reserve_protection_active is True
        released = controller.scan(reported(protection.release_level_m + 0.01), 3.20, 300.0)
        assert released.reserve_protection_active is False

    def test_denial_notification_syncs_controller_state(self, config: BlackstartConfig):
        """Controller timers must not drift out of step with the actuator."""
        controller = LevelController(config.process)
        controller.scan(reported(2.70), 3.20, t_s=100.0)
        assert controller.pump_running is True
        controller.notify_pump_denied(t_s=101.0)
        assert controller.pump_running is False


class TestPlcScanner:
    def test_holds_outputs_between_scans(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        scanner = PlcScanner(controller, scan_interval_s=1.0)
        scanner.execute(reported(3.20), 3.20, t_s=0.0)
        scanner.execute(reported(2.00), 3.20, t_s=0.5)  # inside the scan interval
        assert scanner.scan_count == 1

    def test_rescans_once_the_interval_elapses(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        scanner = PlcScanner(controller, scan_interval_s=1.0)
        scanner.execute(reported(3.20), 3.20, t_s=0.0)
        scanner.execute(reported(3.20), 3.20, t_s=1.0)
        assert scanner.scan_count == 2

    def test_held_output_reports_the_current_setpoint(self, config: BlackstartConfig):
        controller = LevelController(config.process)
        scanner = PlcScanner(controller, scan_interval_s=1.0)
        scanner.execute(reported(3.20), 3.20, t_s=0.0)
        held = scanner.execute(reported(3.20), 3.55, t_s=0.5)
        assert held.setpoint_m == pytest.approx(3.55)
        assert scanner.scan_count == 1

    def test_rejects_a_non_positive_interval(self, config: BlackstartConfig):
        with pytest.raises(ValueError, match="must be positive"):
            PlcScanner(LevelController(config.process), scan_interval_s=0.0)


def make_backstop(config: BlackstartConfig, *, enabled: bool = True) -> EngineeringBackstop:
    """Build a backstop bound to the shipped policy."""
    return EngineeringBackstop(config.architecture.backstop, config.process, enabled=enabled)


def request_at(setpoint_m: float, *, pump_run: bool = True) -> ControlRequest:
    """A control request asking to run the pump toward a setpoint."""
    return ControlRequest(setpoint_m=setpoint_m, pump_run=pump_run, valve_position=1.0)


class TestBackstopDisabled:
    def test_is_a_strict_pass_through(self, config: BlackstartConfig):
        """The control variant must differ in exactly one respect."""
        backstop = make_backstop(config, enabled=False)
        constraint = backstop.constrain_setpoint(9.99, DT)
        assert constraint.effective_setpoint_m == pytest.approx(9.99)
        assert constraint.constrained_by == ()

        decision = backstop.evaluate_permissive(
            request_at(9.99),
            constraint,
            independent_level_m=4.9,
            source_level_m=0.0,
            t_s=100.0,
        )
        assert decision.pump_permitted is True
        assert decision.acted is False

    def test_records_no_activations(self, config: BlackstartConfig):
        backstop = make_backstop(config, enabled=False)
        constraint = backstop.constrain_setpoint(9.99, DT)
        backstop.evaluate_permissive(
            request_at(9.99), constraint, independent_level_m=4.9, source_level_m=0.0, t_s=1.0
        )
        assert set(backstop.activation_counts.values()) == {0}


class TestBackstopSetpointClamp:
    def test_bs01_clamps_an_out_of_range_setpoint(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        maximum = config.architecture.backstop.rule("BS-01").setpoint_max_m
        for _ in range(200):  # allow the slew limiter to converge
            constraint = backstop.constrain_setpoint(4.80, DT)
        assert constraint.effective_setpoint_m == pytest.approx(maximum)
        assert backstop.activation_counts["BS-01"] > 0

    def test_bs01_clamps_below_the_minimum(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        minimum = config.architecture.backstop.rule("BS-01").setpoint_min_m
        for _ in range(200):
            constraint = backstop.constrain_setpoint(0.10, DT)
        assert constraint.effective_setpoint_m == pytest.approx(minimum)

    def test_bs01_leaves_a_legitimate_setpoint_untouched(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        constraint = backstop.constrain_setpoint(3.20, DT)
        assert constraint.effective_setpoint_m == pytest.approx(3.20)
        assert constraint.constrained_by == ()

    def test_bs02_limits_the_slew_rate(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        max_slew = config.architecture.backstop.rule("BS-02").max_slew_m_s
        assert max_slew is not None
        constraint = backstop.constrain_setpoint(3.60, DT)
        moved = abs(constraint.effective_setpoint_m - 3.20)
        assert moved == pytest.approx(max_slew * DT)
        assert "BS-02" in constraint.constrained_by

    def test_clamped_setpoint_cannot_reach_the_safety_limit(self, config: BlackstartConfig):
        """The clamp must hold the process safe on its own, not rely on the trip."""
        clamp = config.architecture.backstop.rule("BS-01").setpoint_max_m
        limit = config.invariants.by_id("INV-001").limit_m
        assert clamp is not None and limit is not None
        assert clamp + config.process.control.deadband_m < limit


class TestBackstopInterlocks:
    def test_bs03_trips_on_the_independent_element(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        trip = config.architecture.backstop.rule("BS-03").trip_level_m
        assert trip is not None
        constraint = backstop.constrain_setpoint(3.20, DT)
        decision = backstop.evaluate_permissive(
            request_at(3.20), constraint, independent_level_m=trip, source_level_m=6.0, t_s=1.0
        )
        assert decision.pump_permitted is False
        assert "BS-03" in decision.denied_by

    def test_bs03_survives_a_falsified_operator_transmitter(self, config: BlackstartConfig):
        """The rule that makes SCN-003 end differently.

        The operator transmitter is irrelevant to this decision by construction:
        the trip reads only the independent element.
        """
        backstop = make_backstop(config)
        constraint = backstop.constrain_setpoint(3.20, DT)
        decision = backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=4.30,  # truth
            source_level_m=6.0,
            t_s=1.0,
        )
        assert decision.pump_permitted is False

    def test_bs03_latches_until_the_reset_level(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        rule = config.architecture.backstop.rule("BS-03")
        assert rule.trip_level_m is not None and rule.reset_level_m is not None
        constraint = backstop.constrain_setpoint(3.20, DT)
        backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=rule.trip_level_m,
            source_level_m=6.0,
            t_s=1.0,
        )
        between = (rule.trip_level_m + rule.reset_level_m) / 2.0
        still_tripped = backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=between,
            source_level_m=6.0,
            t_s=2.0,
        )
        assert still_tripped.pump_permitted is False

        reset = backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=rule.reset_level_m - 0.01,
            source_level_m=6.0,
            t_s=3.0,
        )
        assert reset.pump_permitted is True

    def test_bs04_denies_the_pump_without_suction(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        constraint = backstop.constrain_setpoint(3.20, DT)
        decision = backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=2.0,
            source_level_m=config.process.source.suction_limit_m,
            t_s=1.0,
        )
        assert decision.pump_permitted is False
        assert "BS-04" in decision.denied_by

    def test_bs05_enforces_a_minimum_off_time(self, config: BlackstartConfig):
        """BS-05 is redundant with the controller's own anti-cycling in the
        shipped scenarios, so it is driven directly here."""
        backstop = make_backstop(config)
        constraint = backstop.constrain_setpoint(3.20, DT)
        # Run, then trip, so the backstop records a denial timestamp.
        backstop.evaluate_permissive(
            request_at(3.20), constraint, independent_level_m=2.0, source_level_m=6.0, t_s=0.0
        )
        backstop.evaluate_permissive(
            request_at(3.20),
            constraint,
            independent_level_m=2.0,
            source_level_m=config.process.source.suction_limit_m,
            t_s=1.0,
        )
        # Suction restored, but well inside the minimum off time.
        decision = backstop.evaluate_permissive(
            request_at(3.20), constraint, independent_level_m=2.0, source_level_m=6.0, t_s=5.0
        )
        assert decision.pump_permitted is False
        assert "BS-05" in decision.denied_by

    def test_permits_normal_operation(self, config: BlackstartConfig):
        backstop = make_backstop(config)
        constraint = backstop.constrain_setpoint(3.20, DT)
        decision = backstop.evaluate_permissive(
            request_at(3.20), constraint, independent_level_m=3.0, source_level_m=6.0, t_s=1.0
        )
        assert decision.pump_permitted is True
        assert decision.acted is False


class TestBackstopIndependence:
    def test_thresholds_are_not_writable_at_runtime(self, config: BlackstartConfig):
        """Policy must not be reconfigurable through any simulated command path."""
        backstop = make_backstop(config)
        summary_before = backstop.summary()["thresholds"]
        for _ in range(50):
            constraint = backstop.constrain_setpoint(99.0, DT)
            backstop.evaluate_permissive(
                request_at(99.0),
                constraint,
                independent_level_m=9.0,
                source_level_m=0.0,
                t_s=1.0,
            )
        assert backstop.summary()["thresholds"] == summary_before

    def test_shares_no_code_with_the_invariant_checker(self, repo_root):
        """Otherwise 'backstop enabled implies no violations' is a tautology.

        Checked by AST so that prose describing the boundary is not mistaken for
        code crossing it.
        """
        backstop_imports = imported_modules(repo_root / "blackstart" / "controller" / "backstop.py")
        assert not any(m.startswith("blackstart.core.invariants") for m in backstop_imports)

        for source in python_sources(repo_root / "blackstart" / "core" / "invariants"):
            invariant_imports = imported_modules(source)
            assert not any(m.startswith("blackstart.controller") for m in invariant_imports), (
                f"{source.name} imports the control layer"
            )

    def test_rejects_missing_policy_thresholds(self, config: BlackstartConfig):
        """A safety constraint must never silently default."""
        rules = [
            rule.model_copy(update={"trip_level_m": None}) if rule.id == "BS-03" else rule
            for rule in config.architecture.backstop.rules
        ]
        broken = config.architecture.backstop.model_copy(update={"rules": rules})
        with pytest.raises(ValueError, match=r"BS-03\.trip_level_m"):
            EngineeringBackstop(broken, config.process, enabled=True)
