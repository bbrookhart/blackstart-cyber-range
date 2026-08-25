"""Deterministic hydraulic model of the storage and pumping process.

The governing equations are documented in ``docs/physical-model.md`` and fixed by
ADR-002. Every parameter is synthetic.

Mass balance over the tank:

.. code-block:: text

    dL/dt = (q_in - q_out) / A

Pump inflow follows a linear pump curve, so delivered flow falls as static head
rises:

.. code-block:: text

    q_in = energised * q_nominal * clamp(1 - L / H_shutoff, 0, 1)

Outlet flow is gravity discharge through a throttling valve (Torricelli),
limited by what the customer actually asks for:

.. code-block:: text

    q_capacity = position * C_d * A_orifice * sqrt(2 * g * L)
    q_out      = min(demand, q_capacity)

Service shortfall is therefore *emergent* from the hydraulics rather than a flag
someone sets, which is what makes the C2/C3 consequence classes meaningful.

The flow helpers are module-level pure functions so they can be tested and
reasoned about independently of any simulation state.
"""

from __future__ import annotations

import math

from blackstart.core.config import ProcessConfig
from blackstart.core.models import TruthState

__all__ = ["WaterProcessModel", "pump_inflow_m3_s", "valve_capacity_m3_s"]


def pump_inflow_m3_s(
    tank_level_m: float,
    source_level_m: float,
    pump_energised: bool,
    config: ProcessConfig,
) -> float:
    """Compute pump delivery against the current static head.

    Returns zero when the pump is de-energised, and also when the source level
    has fallen to or below the suction limit. In the latter case the motor
    remains energised while delivering nothing: the dry-run condition that
    INV-003 exists to detect. Returning zero flow here is what makes that
    condition physically real rather than merely annotated.

    Args:
        tank_level_m: Current tank level, metres. Static head on the pump.
        source_level_m: Current source reservoir level, metres.
        pump_energised: Whether the pump motor is running.
        config: Process configuration supplying the pump curve.

    Returns:
        Volumetric inflow in m3/s, never negative.
    """
    if not pump_energised:
        return 0.0
    if source_level_m <= config.source.suction_limit_m:
        return 0.0
    head_fraction = 1.0 - (tank_level_m / config.pump.shutoff_head_m)
    # A pump cannot deliver negative flow, and cannot exceed its nominal rating.
    head_fraction = min(1.0, max(0.0, head_fraction))
    return config.pump.nominal_flow_m3_s * head_fraction


def valve_capacity_m3_s(
    tank_level_m: float,
    valve_position: float,
    config: ProcessConfig,
) -> float:
    """Compute the maximum gravity discharge available at the current level.

    Args:
        tank_level_m: Current tank level, metres. Drives the discharge head.
        valve_position: Valve opening in ``[0, 1]``.
        config: Process configuration supplying valve geometry and gravity.

    Returns:
        Maximum deliverable outflow in m3/s, never negative.
    """
    if tank_level_m <= 0.0 or valve_position <= 0.0:
        return 0.0
    velocity_m_s = math.sqrt(2.0 * config.simulation.gravity_m_s2 * tank_level_m)
    position = min(1.0, max(0.0, valve_position))
    return (
        position * config.valve.discharge_coefficient * config.valve.orifice_area_m2 * velocity_m_s
    )


class WaterProcessModel:
    """Explicit-Euler integrator for the storage and pumping process.

    The model is stateless with respect to the simulation: it reads and writes a
    :class:`~blackstart.core.models.TruthState` passed in by the caller. This
    keeps ownership of state in the runner and makes a step trivially replayable
    in a test.
    """

    def __init__(self, config: ProcessConfig) -> None:
        """Bind the model to a validated process configuration."""
        self._config = config

    @property
    def config(self) -> ProcessConfig:
        """The process configuration this model integrates."""
        return self._config

    def initial_state(self) -> TruthState:
        """Build the ground-truth state at ``t = 0`` from configuration."""
        return TruthState(
            tank_level_m=self._config.tank.initial_level_m,
            source_level_m=self._config.source.initial_level_m,
            pump_energised=self._config.pump.initial_state == "on",
            valve_position=self._config.valve.initial_position,
        )

    def slew_valve(self, current_position: float, commanded_position: float, dt_s: float) -> float:
        """Move the valve toward its commanded position within the actuator slew limit.

        Actuators have finite travel speed. Enforcing that here is what makes a
        commanded step change physically impossible, which is the physical half
        of the INV-004 command-rate constraint.
        """
        target = min(1.0, max(0.0, commanded_position))
        max_travel = self._config.valve.max_slew_per_s * dt_s
        delta = target - current_position
        if abs(delta) <= max_travel:
            return target
        return current_position + math.copysign(max_travel, delta)

    def step(self, state: TruthState, demand_m3_s: float, dt_s: float) -> TruthState:
        """Advance the physical state by one timestep.

        The caller is responsible for having already set ``pump_energised`` and
        ``valve_position`` on ``state`` from the (backstop-filtered) command, and
        for having applied any scenario effect to ``source_level_m``.

        Args:
            state: Ground-truth state, mutated in place and returned.
            demand_m3_s: Downstream demand for this timestep.
            dt_s: Integration timestep in seconds.

        Returns:
            The same ``state`` object, advanced by ``dt_s``.
        """
        area_m2 = self._config.tank.area_m2
        overflow_m = self._config.tank.overflow_height_m

        inflow = pump_inflow_m3_s(
            state.tank_level_m, state.source_level_m, state.pump_energised, self._config
        )
        capacity = valve_capacity_m3_s(state.tank_level_m, state.valve_position, self._config)
        outflow = min(demand_m3_s, capacity)

        # A tank cannot supply more than it holds. Bounding outflow by the
        # available volume (plus what arrives this step) is what guarantees the
        # level never integrates negative -- see the corresponding property test.
        available_m3_s = (state.tank_level_m * area_m2) / dt_s + inflow
        outflow = min(outflow, max(0.0, available_m3_s))

        level = state.tank_level_m + ((inflow - outflow) / area_m2) * dt_s

        # Volume driven above the weir crest leaves the system. The safe limit
        # (INV-001) sits below this height, so a safety excursion is observable
        # well before containment is lost.
        spill_rate = 0.0
        if level > overflow_m:
            spill_volume_m3 = (level - overflow_m) * area_m2
            spill_rate = spill_volume_m3 / dt_s
            state.spill_volume_m3 += spill_volume_m3
            level = overflow_m
        elif level < 0.0:
            # Defensive: the outflow bound above should make this unreachable.
            level = 0.0

        state.tank_level_m = level
        state.inflow_m3_s = inflow
        state.outflow_m3_s = outflow
        state.demand_m3_s = demand_m3_s
        state.spill_rate_m3_s = spill_rate
        return state
