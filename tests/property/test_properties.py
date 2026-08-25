"""Property-based tests.

Unit tests check the cases someone thought of. These check invariants of the
model that must hold across the whole input space -- particularly the physical
bounds, whose violation would silently invalidate every result rather than
producing an obvious failure.
"""

from __future__ import annotations

import random

import pytest
from blackstart.controller.backstop import EngineeringBackstop
from blackstart.controller.control_logic import ControlRequest
from blackstart.core.config import BlackstartConfig
from blackstart.core.consequence.classifier import ConsequenceClassifier
from blackstart.core.invariants.engine import InvariantStepResult
from blackstart.core.models import ConsequenceLevel
from blackstart.core.physics.process import (
    WaterProcessModel,
    pump_inflow_m3_s,
    valve_capacity_m3_s,
)
from blackstart.scenario_engine.loader import load_scenario
from blackstart.scenario_engine.orchestration import ExperimentRunner, resolve_variant
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.conftest import make_state

pytestmark = pytest.mark.property

# Simulation runs are not cheap; keep example counts modest but meaningful.
PROFILE = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

levels = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
source_levels = st.floats(min_value=0.0, max_value=8.0, allow_nan=False)
demands = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
positions = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
setpoints = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False)


class TestPhysicalBounds:
    @PROFILE
    @given(
        level=levels,
        source=source_levels,
        demand=demands,
        position=positions,
        energised=st.booleans(),
    )
    def test_level_stays_within_the_tank(
        self,
        config: BlackstartConfig,
        level: float,
        source: float,
        demand: float,
        position: float,
        energised: bool,
    ):
        """The single most important physical property: no step, from any
        reachable state, can produce a level outside the tank."""
        physics = WaterProcessModel(config.process)
        state = physics.initial_state()
        state.tank_level_m = level
        state.source_level_m = source
        state.pump_energised = energised
        state.valve_position = position

        physics.step(state, demand_m3_s=demand, dt_s=config.process.simulation.timestep_s)

        assert state.tank_level_m >= 0.0
        assert state.tank_level_m <= config.process.tank.overflow_height_m

    @PROFILE
    @given(level=levels, source=source_levels, demand=demands, position=positions)
    def test_flows_are_never_negative(
        self,
        config: BlackstartConfig,
        level: float,
        source: float,
        demand: float,
        position: float,
    ):
        physics = WaterProcessModel(config.process)
        state = physics.initial_state()
        state.tank_level_m = level
        state.source_level_m = source
        state.pump_energised = True
        state.valve_position = position

        physics.step(state, demand_m3_s=demand, dt_s=0.5)

        assert state.inflow_m3_s >= 0.0
        assert state.outflow_m3_s >= 0.0
        assert state.spill_volume_m3 >= 0.0

    @PROFILE
    @given(level=levels, position=positions, demand=demands)
    def test_delivered_flow_never_exceeds_demand_or_capacity(
        self, config: BlackstartConfig, level: float, position: float, demand: float
    ):
        physics = WaterProcessModel(config.process)
        state = physics.initial_state()
        state.tank_level_m = level
        state.valve_position = position
        capacity = valve_capacity_m3_s(level, position, config.process)

        physics.step(state, demand_m3_s=demand, dt_s=0.5)

        assert state.outflow_m3_s <= demand + 1e-9
        assert state.outflow_m3_s <= capacity + 1e-9

    @PROFILE
    @given(level=levels, source=source_levels)
    def test_pump_delivery_never_increases_with_head(
        self, config: BlackstartConfig, level: float, source: float
    ):
        higher = min(config.process.tank.overflow_height_m, level + 0.25)
        low = pump_inflow_m3_s(level, source, True, config.process)
        high = pump_inflow_m3_s(higher, source, True, config.process)
        assert high <= low + 1e-12

    @PROFILE
    @given(
        current=positions,
        commanded=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
        dt=st.floats(min_value=0.01, max_value=5.0, allow_nan=False),
    )
    def test_valve_position_stays_in_range(
        self, config: BlackstartConfig, current: float, commanded: float, dt: float
    ):
        physics = WaterProcessModel(config.process)
        assert 0.0 <= physics.slew_valve(current, commanded, dt) <= 1.0

    @PROFILE
    @given(
        current=positions,
        commanded=positions,
        dt=st.floats(min_value=0.01, max_value=5.0, allow_nan=False),
    )
    def test_valve_travel_respects_the_slew_limit(
        self, config: BlackstartConfig, current: float, commanded: float, dt: float
    ):
        physics = WaterProcessModel(config.process)
        moved = abs(physics.slew_valve(current, commanded, dt) - current)
        assert moved <= config.process.valve.max_slew_per_s * dt + 1e-9

    @PROFILE
    @given(steps=st.lists(st.tuples(demands, st.booleans()), min_size=1, max_size=40))
    def test_spill_volume_is_monotonically_non_decreasing(
        self, config: BlackstartConfig, steps: list[tuple[float, bool]]
    ):
        physics = WaterProcessModel(config.process)
        state = physics.initial_state()
        previous = state.spill_volume_m3
        for demand, energised in steps:
            state.pump_energised = energised
            physics.step(state, demand_m3_s=demand, dt_s=0.5)
            assert state.spill_volume_m3 >= previous
            previous = state.spill_volume_m3


class TestBackstopProperties:
    @PROFILE
    @given(requested=setpoints, steps=st.integers(min_value=1, max_value=400))
    def test_effective_setpoint_never_leaves_the_permitted_range(
        self, config: BlackstartConfig, requested: float, steps: int
    ):
        """No requested value, however extreme, can move the effective setpoint
        outside the engineering range."""
        rule = config.architecture.backstop.rule("BS-01")
        assert rule.setpoint_min_m is not None and rule.setpoint_max_m is not None
        backstop = EngineeringBackstop(config.architecture.backstop, config.process, enabled=True)
        for _ in range(steps):
            constraint = backstop.constrain_setpoint(requested, 0.5)
            assert rule.setpoint_min_m - 1e-9 <= constraint.effective_setpoint_m
            assert constraint.effective_setpoint_m <= rule.setpoint_max_m + 1e-9

    @PROFILE
    @given(requested=setpoints)
    def test_setpoint_never_moves_faster_than_the_slew_limit(
        self, config: BlackstartConfig, requested: float
    ):
        max_slew = config.architecture.backstop.rule("BS-02").max_slew_m_s
        assert max_slew is not None
        backstop = EngineeringBackstop(config.architecture.backstop, config.process, enabled=True)
        previous = config.process.control.operator_setpoint_m
        for _ in range(50):
            effective = backstop.constrain_setpoint(requested, 0.5).effective_setpoint_m
            assert abs(effective - previous) <= max_slew * 0.5 + 1e-9
            previous = effective

    @PROFILE
    @given(
        independent=st.floats(min_value=0.0, max_value=6.0, allow_nan=False),
        source=source_levels,
        requested=setpoints,
    )
    def test_pump_is_never_permitted_above_the_trip_level(
        self,
        config: BlackstartConfig,
        independent: float,
        source: float,
        requested: float,
    ):
        """The forbidden transition the backstop exists to prevent."""
        rule = config.architecture.backstop.rule("BS-03")
        assert rule.trip_level_m is not None
        backstop = EngineeringBackstop(config.architecture.backstop, config.process, enabled=True)
        constraint = backstop.constrain_setpoint(requested, 0.5)
        decision = backstop.evaluate_permissive(
            ControlRequest(setpoint_m=requested, pump_run=True, valve_position=1.0),
            constraint,
            independent_level_m=independent,
            source_level_m=source,
            t_s=100.0,
        )
        if independent >= rule.trip_level_m:
            assert decision.pump_permitted is False
        if source <= config.process.source.suction_limit_m:
            assert decision.pump_permitted is False

    @PROFILE
    @given(requested=setpoints, independent=levels, source=source_levels)
    def test_disabled_backstop_is_always_a_pass_through(
        self,
        config: BlackstartConfig,
        requested: float,
        independent: float,
        source: float,
    ):
        """The control variant must never differ in any respect but the constraint."""
        backstop = EngineeringBackstop(config.architecture.backstop, config.process, enabled=False)
        constraint = backstop.constrain_setpoint(requested, 0.5)
        request = ControlRequest(setpoint_m=requested, pump_run=True, valve_position=0.7)
        decision = backstop.evaluate_permissive(
            request,
            constraint,
            independent_level_m=independent,
            source_level_m=source,
            t_s=100.0,
        )
        assert decision.effective_setpoint_m == requested
        assert decision.pump_permitted is True
        assert decision.valve_position == pytest.approx(0.7)
        assert decision.acted is False


class TestConsequenceProperties:
    @PROFILE
    @given(
        levels_seen=st.lists(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
            min_size=1,
            max_size=60,
        )
    )
    def test_maximum_consequence_is_monotonic(
        self, config: BlackstartConfig, levels_seen: list[float]
    ):
        """The recorded maximum may never decrease, whatever the process does."""
        classifier = ConsequenceClassifier(config.consequences)
        empty = InvariantStepResult(t_s=0.0, samples=())
        highest = ConsequenceLevel.C0
        for index, level in enumerate(levels_seen):
            classifier.classify(make_state(t_s=index * 0.5, tank_level_m=level), empty, 0.5)
            assert classifier.maximum_level >= highest
            highest = classifier.maximum_level

    @PROFILE
    @given(
        demand=st.floats(min_value=0.001, max_value=1.0, allow_nan=False),
        delivered_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_shortfall_ratio_stays_in_the_unit_interval(
        self, config: BlackstartConfig, demand: float, delivered_fraction: float
    ):
        state = make_state(demand_m3_s=demand, outflow_m3_s=demand * delivered_fraction)
        assert 0.0 <= state.truth.service_shortfall_ratio <= 1.0


class TestDeterminism:
    @PROFILE
    @given(seed=st.integers(min_value=0, max_value=100_000))
    def test_identical_seeds_produce_identical_traces(self, config: BlackstartConfig, seed: int):
        """The determinism contract, over arbitrary seeds (ADR-005)."""
        scenario = load_scenario("SCN-001").model_copy(update={"duration_s": 60.0})
        variant = resolve_variant("backstop-enabled")

        first = ExperimentRunner(config, scenario, variant, seed_override=seed).run()
        second = ExperimentRunner(config, scenario, variant, seed_override=seed).run()

        assert first.experiment_id == second.experiment_id
        assert first.trace.rows == second.trace.rows

    @PROFILE
    @given(seed=st.integers(min_value=0, max_value=1000))
    def test_experiments_never_consume_global_random_state(
        self, config: BlackstartConfig, seed: int
    ):
        """A stray draw from the global generator would silently destroy
        reproducibility, and would do so without any visible failure.

        Probes the real module-level state: seed it, take a reference draw,
        re-seed, run a full experiment, and draw again. The two draws can only
        differ if the experiment consumed global entropy.
        """
        scenario = load_scenario("SCN-001").model_copy(update={"duration_s": 30.0})
        variant = resolve_variant("backstop-enabled")

        random.seed(12345)
        reference = random.random()

        random.seed(12345)
        ExperimentRunner(config, scenario, variant, seed_override=seed).run()
        after = random.random()

        assert after == reference
