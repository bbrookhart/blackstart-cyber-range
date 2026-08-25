"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from random import Random

import pytest
from blackstart.core.config import BlackstartConfig, load_config
from blackstart.core.graph.build import build_graph, load_asset_model
from blackstart.core.models import CommandState, ProcessState, ReportedState, TruthState
from blackstart.core.physics.process import WaterProcessModel

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root directory."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def config() -> BlackstartConfig:
    """The shipped BLACKSTART configuration.

    Session-scoped and frozen: every configuration model is immutable, so a test
    cannot mutate it and affect another.
    """
    return load_config()


@pytest.fixture
def physics(config: BlackstartConfig) -> WaterProcessModel:
    """A process model bound to the shipped configuration."""
    return WaterProcessModel(config.process)


@pytest.fixture
def rng() -> Random:
    """A seeded generator for tests that need instrument noise."""
    return Random(20260824)


@pytest.fixture(scope="session")
def consequence_graph(config: BlackstartConfig):
    """The consequence dependency graph built from shipped configuration."""
    return build_graph(load_asset_model(), config.invariants, config.consequences)


def make_state(
    *,
    t_s: float = 0.0,
    tank_level_m: float = 3.20,
    reported_level_m: float | None = None,
    source_level_m: float = 6.0,
    pump_energised: bool = False,
    valve_position: float = 1.0,
    demand_m3_s: float = 0.035,
    outflow_m3_s: float = 0.035,
    inflow_m3_s: float = 0.0,
    spill_volume_m3: float = 0.0,
    requested_setpoint_m: float = 3.20,
    effective_setpoint_m: float | None = None,
    pump_starts: int = 0,
    independent_level_m: float | None = None,
    supervisory_available: bool = True,
) -> ProcessState:
    """Build a fully specified :class:`ProcessState` for invariant tests.

    Defaults describe a healthy process at the operator setpoint, so a test only
    states the one thing it is varying.
    """
    truth = TruthState(
        tank_level_m=tank_level_m,
        source_level_m=source_level_m,
        pump_energised=pump_energised,
        valve_position=valve_position,
        inflow_m3_s=inflow_m3_s,
        outflow_m3_s=outflow_m3_s,
        demand_m3_s=demand_m3_s,
        spill_volume_m3=spill_volume_m3,
    )
    reported = ReportedState(
        tank_level_m=tank_level_m if reported_level_m is None else reported_level_m,
        inflow_m3_s=inflow_m3_s,
        outflow_m3_s=outflow_m3_s,
        pump_energised=pump_energised,
        valve_position=valve_position,
        supervisory_available=supervisory_available,
    )
    command = CommandState(
        requested_setpoint_m=requested_setpoint_m,
        effective_setpoint_m=(
            requested_setpoint_m if effective_setpoint_m is None else effective_setpoint_m
        ),
        pump_starts=pump_starts,
    )
    return ProcessState(
        t_s=t_s,
        truth=truth,
        reported=reported,
        command=command,
        independent_level_m=(tank_level_m if independent_level_m is None else independent_level_m),
    )
