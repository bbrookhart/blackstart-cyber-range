"""Instrumentation and demand models.

These are the two places where the simulation's only stochastic inputs enter, and
both draw from a single explicitly seeded generator threaded through the runner.
No module in BLACKSTART touches the global :mod:`random` state; a test asserts
this, because a stray global draw would silently destroy reproducibility.

The sensor model is also where telemetry-integrity effects act. It carries
mutable fault fields written *only* by the scenario effect layer
(:mod:`blackstart.scenario_engine.effects`). Faults change what is reported; they
never reach :class:`~blackstart.core.models.TruthState`.
"""

from __future__ import annotations

from random import Random

from blackstart.core.config import ProcessConfig
from blackstart.core.models import ReportedState, TruthState

__all__ = ["DemandModel", "SensorModel"]


def _quantise(value: float, resolution_m: float) -> float:
    """Round ``value`` to the instrument's reporting resolution."""
    return round(value / resolution_m) * resolution_m


class SensorModel:
    """Produces the reported view of the process from ground truth.

    Attributes prefixed ``fault_`` represent a degraded or manipulated
    instrument. They are written exclusively by scenario effects and default to
    a healthy instrument.
    """

    def __init__(self, config: ProcessConfig, rng: Random) -> None:
        """Bind the instrument model to configuration and a seeded generator."""
        self._config = config
        self._rng = rng
        self._last_reported_level_m: float | None = None

        #: Constant offset added to the reported level (``sensor.bias`` effect).
        self.fault_level_bias_m: float = 0.0
        #: When true the transmitter holds its last reported value
        #: (``sensor.freeze`` effect).
        self.fault_level_frozen: bool = False
        #: When false the supervisory telemetry path is unavailable
        #: (``supervisory.blackout`` effect). Local control is unaffected.
        self.fault_supervisory_available: bool = True

    def read(self, truth: TruthState) -> ReportedState:
        """Sample the process and produce the control system's view of it.

        Args:
            truth: Ground-truth state. Read only; never modified here.

        Returns:
            The reported state, including any active instrument fault.
        """
        level_noise = self._rng.gauss(0.0, self._config.sensors.level_transmitter.noise_std_m)
        flow_noise_in = self._rng.gauss(0.0, self._config.sensors.flow_meter.noise_std_m3_s)
        flow_noise_out = self._rng.gauss(0.0, self._config.sensors.flow_meter.noise_std_m3_s)

        if self.fault_level_frozen and self._last_reported_level_m is not None:
            # A frozen transmitter repeats its last value indefinitely: the
            # trend looks plausible and stable, which is precisely why this
            # condition is hard to notice from the operator view alone.
            reported_level = self._last_reported_level_m
        else:
            raw = truth.tank_level_m + level_noise + self.fault_level_bias_m
            reported_level = _quantise(
                max(0.0, raw), self._config.sensors.level_transmitter.resolution_m
            )
            self._last_reported_level_m = reported_level

        return ReportedState(
            tank_level_m=reported_level,
            inflow_m3_s=max(0.0, truth.inflow_m3_s + flow_noise_in),
            outflow_m3_s=max(0.0, truth.outflow_m3_s + flow_noise_out),
            pump_energised=truth.pump_energised,
            valve_position=truth.valve_position,
            supervisory_available=self.fault_supervisory_available,
        )

    def read_independent_element(self, truth: TruthState) -> float:
        """Sample the independent level element used by the engineering backstop.

        Deliberately unaffected by every ``fault_`` field above. That
        independence is a modelling assumption stated in
        ``configs/process.yaml`` and ``docs/limitations.md`` -- a real
        independent element can itself be compromised, and BLACKSTART does not
        claim otherwise. It is the assumption SCN-003 is designed to exercise.
        """
        noise = self._rng.gauss(0.0, self._config.independent_level_element.noise_std_m)
        return _quantise(
            max(0.0, truth.tank_level_m + noise),
            self._config.independent_level_element.resolution_m,
        )


class DemandModel:
    """Synthetic downstream consumption.

    ``base_rate_m3_s`` is mutable so that ``demand.step`` and ``demand.ramp``
    effects can drive a benign physical disturbance. Those effects are the
    control case for the whole project: BLACKSTART must be able to distinguish an
    ordinary load disturbance from a cyber-originated condition (SCN-002).
    """

    def __init__(self, config: ProcessConfig, rng: Random) -> None:
        """Bind the demand model to configuration and a seeded generator."""
        self._config = config
        self._rng = rng
        #: Current base demand. Written by ``demand.*`` scenario effects.
        self.base_rate_m3_s: float = config.demand.base_rate_m3_s

    def sample(self) -> float:
        """Draw the demand for the current timestep.

        Returns:
            Demand in m3/s: the base rate perturbed by a bounded uniform
            variation drawn from the seeded generator. Never negative.
        """
        spread = self._config.demand.variation_fraction
        variation = spread * (2.0 * self._rng.random() - 1.0)
        return max(0.0, self.base_rate_m3_s * (1.0 + variation))
