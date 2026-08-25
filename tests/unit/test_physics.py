"""Unit tests for the hydraulic model.

These verify the equations in ADR-002 directly, against values computed by hand,
rather than against whatever the implementation happens to produce.
"""

from __future__ import annotations

import math

import pytest
from blackstart.core.config import BlackstartConfig
from blackstart.core.physics.process import (
    WaterProcessModel,
    pump_inflow_m3_s,
    valve_capacity_m3_s,
)

pytestmark = pytest.mark.unit


class TestPumpCurve:
    def test_delivers_nothing_when_de_energised(self, config: BlackstartConfig):
        assert pump_inflow_m3_s(3.0, 6.0, False, config.process) == 0.0

    def test_follows_the_linear_curve(self, config: BlackstartConfig):
        # q = q_nominal * (1 - L / H_shutoff) = 0.200 * (1 - 3.25/6.5) = 0.100
        assert pump_inflow_m3_s(3.25, 6.0, True, config.process) == pytest.approx(0.100)

    def test_delivery_falls_as_head_rises(self, config: BlackstartConfig):
        low = pump_inflow_m3_s(1.0, 6.0, True, config.process)
        high = pump_inflow_m3_s(4.0, 6.0, True, config.process)
        assert low > high > 0.0

    def test_delivers_nothing_above_shutoff_head(self, config: BlackstartConfig):
        above = config.process.pump.shutoff_head_m + 1.0
        assert pump_inflow_m3_s(above, 6.0, True, config.process) == 0.0

    def test_loses_suction_below_the_source_limit(self, config: BlackstartConfig):
        """The damaging case: energised, drawing current, delivering nothing."""
        limit = config.process.source.suction_limit_m
        assert pump_inflow_m3_s(3.0, limit, True, config.process) == 0.0
        assert pump_inflow_m3_s(3.0, limit - 0.01, True, config.process) == 0.0
        assert pump_inflow_m3_s(3.0, limit + 0.01, True, config.process) > 0.0


class TestValveDischarge:
    def test_follows_torricelli(self, config: BlackstartConfig):
        process = config.process
        level = 3.0
        expected = (
            1.0
            * process.valve.discharge_coefficient
            * process.valve.orifice_area_m2
            * math.sqrt(2.0 * process.simulation.gravity_m_s2 * level)
        )
        assert valve_capacity_m3_s(level, 1.0, process) == pytest.approx(expected)

    def test_scales_linearly_with_position(self, config: BlackstartConfig):
        full = valve_capacity_m3_s(3.0, 1.0, config.process)
        half = valve_capacity_m3_s(3.0, 0.5, config.process)
        assert half == pytest.approx(full * 0.5)

    @pytest.mark.parametrize(("level", "position"), [(0.0, 1.0), (3.0, 0.0), (-1.0, 1.0)])
    def test_no_discharge_without_head_or_opening(
        self, config: BlackstartConfig, level: float, position: float
    ):
        assert valve_capacity_m3_s(level, position, config.process) == 0.0


class TestIntegration:
    def test_mass_balance_over_one_step(self, physics: WaterProcessModel):
        state = physics.initial_state()
        state.pump_energised = True
        before = state.tank_level_m
        area = physics.config.tank.area_m2
        dt = physics.config.simulation.timestep_s

        physics.step(state, demand_m3_s=0.035, dt_s=dt)

        expected = before + (state.inflow_m3_s - state.outflow_m3_s) / area * dt
        assert state.tank_level_m == pytest.approx(expected)

    def test_delivered_flow_is_bounded_by_demand(self, physics: WaterProcessModel):
        state = physics.initial_state()
        physics.step(state, demand_m3_s=0.010, dt_s=0.5)
        assert state.outflow_m3_s == pytest.approx(0.010)

    def test_delivered_flow_is_bounded_by_hydraulic_capacity(self, physics: WaterProcessModel):
        """Service shortfall must emerge from the hydraulics, not from a flag."""
        state = physics.initial_state()
        state.tank_level_m = 0.30
        capacity = valve_capacity_m3_s(0.30, 1.0, physics.config)
        physics.step(state, demand_m3_s=1.0, dt_s=0.5)
        assert state.outflow_m3_s == pytest.approx(capacity, rel=1e-6)
        assert state.service_shortfall_ratio > 0.9

    def test_overtopping_spills_and_clamps_at_the_weir(self, physics: WaterProcessModel):
        state = physics.initial_state()
        state.tank_level_m = physics.config.tank.overflow_height_m - 0.001
        state.source_level_m = 6.0
        state.pump_energised = True

        physics.step(state, demand_m3_s=0.0, dt_s=0.5)

        assert state.tank_level_m == pytest.approx(physics.config.tank.overflow_height_m)
        assert state.spill_volume_m3 > 0.0
        assert state.spill_rate_m3_s > 0.0

    def test_spill_volume_accumulates(self, physics: WaterProcessModel):
        state = physics.initial_state()
        state.tank_level_m = physics.config.tank.overflow_height_m
        state.pump_energised = True
        physics.step(state, demand_m3_s=0.0, dt_s=0.5)
        first = state.spill_volume_m3
        physics.step(state, demand_m3_s=0.0, dt_s=0.5)
        assert state.spill_volume_m3 > first

    def test_level_cannot_be_driven_negative(self, physics: WaterProcessModel):
        """The outflow bound, not a clamp, is what keeps the level physical."""
        state = physics.initial_state()
        state.tank_level_m = 0.01
        for _ in range(50):
            physics.step(state, demand_m3_s=5.0, dt_s=0.5)
            assert state.tank_level_m >= 0.0

    def test_safe_limit_sits_below_the_weir(self, config: BlackstartConfig):
        """A safety excursion must be representable, not clamped away (ADR-002)."""
        limit = config.invariants.by_id("INV-001").limit_m
        assert limit is not None
        assert limit < config.process.tank.overflow_height_m


class TestValveSlew:
    def test_reaches_target_within_slew_limit(self, physics: WaterProcessModel):
        assert physics.slew_valve(0.50, 0.52, 1.0) == pytest.approx(0.52)

    def test_limits_travel_when_target_is_far(self, physics: WaterProcessModel):
        max_slew = physics.config.valve.max_slew_per_s
        assert physics.slew_valve(0.0, 1.0, 1.0) == pytest.approx(max_slew)

    def test_limits_travel_in_the_closing_direction(self, physics: WaterProcessModel):
        max_slew = physics.config.valve.max_slew_per_s
        assert physics.slew_valve(1.0, 0.0, 1.0) == pytest.approx(1.0 - max_slew)

    def test_clamps_commanded_position_into_range(self, physics: WaterProcessModel):
        assert physics.slew_valve(1.0, 5.0, 100.0) == pytest.approx(1.0)
        assert physics.slew_valve(0.0, -5.0, 100.0) == pytest.approx(0.0)
