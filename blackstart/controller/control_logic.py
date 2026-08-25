"""Supervisory control logic for the storage and pumping process.

Hysteresis (bang-bang) level control with anti-cycling constraints, plus an
outlet-throttling policy that defends the operational reserve.

The controller acts on the **reported** level, never on ground truth. That is not
a simplification -- it is the modelling decision that makes loss of telemetry
integrity a real phenomenon rather than an annotation. A controller reading truth
would be immune to SCN-003 for reasons no real control system enjoys.

The controller is *not* a safety device. It has no independent measurement and it
will faithfully pursue whatever setpoint it is given, including one that would
drive the process into an unsafe state. Preventing that is the job of the
engineering backstop (:mod:`blackstart.controller.backstop`), which is a
deliberately separate component.
"""

from __future__ import annotations

from dataclasses import dataclass

from blackstart.core.config import ProcessConfig
from blackstart.core.models import ReportedState

__all__ = ["ControlRequest", "LevelController"]


@dataclass(frozen=True, slots=True)
class ControlRequest:
    """A control action requested by the controller, before any constraint."""

    setpoint_m: float
    pump_run: bool
    valve_position: float
    #: Whether reserve protection is throttling the outlet this scan.
    reserve_protection_active: bool = False


class LevelController:
    """Hysteresis level controller with anti-cycling and reserve protection.

    Carries pump timing state; a fresh instance is required per experiment.
    """

    def __init__(self, config: ProcessConfig) -> None:
        """Bind the controller to a validated process configuration."""
        self._config = config
        self._pump_running = config.pump.initial_state == "on"
        self._last_start_t_s = -config.control.min_run_time_s
        self._last_stop_t_s = -config.control.min_off_time_s
        self._pump_starts = 0
        self._reserve_protection_active = False

    @property
    def pump_running(self) -> bool:
        """Whether the controller currently commands the pump to run."""
        return self._pump_running

    @property
    def pump_starts(self) -> int:
        """Cumulative count of pump starts commanded."""
        return self._pump_starts

    def notify_pump_denied(self, t_s: float) -> None:
        """Record that a downstream constraint refused the pump-run permissive.

        The controller must not keep believing the pump is running once the
        backstop has denied it, or its anti-cycling timers would drift out of
        step with the actuator. This is the only channel through which the
        backstop influences controller state, and it carries no authority --
        only the fact that the actuator did not move.
        """
        if self._pump_running:
            self._pump_running = False
            self._last_stop_t_s = t_s

    def scan(self, reported: ReportedState, setpoint_m: float, t_s: float) -> ControlRequest:
        """Execute one control scan.

        Args:
            reported: Instrumented view of the process. Ground truth is not
                available to the controller.
            setpoint_m: The effective level setpoint for this scan.
            t_s: Current simulation time in seconds.

        Returns:
            The requested control action, before backstop evaluation.
        """
        control = self._config.control
        band_lower_m = setpoint_m - control.deadband_m
        band_upper_m = setpoint_m + control.deadband_m
        level = reported.tank_level_m

        if self._pump_running:
            stop_permitted = (t_s - self._last_start_t_s) >= control.min_run_time_s
            if level >= band_upper_m and stop_permitted:
                self._pump_running = False
                self._last_stop_t_s = t_s
        else:
            start_permitted = (t_s - self._last_stop_t_s) >= control.min_off_time_s
            if level <= band_lower_m and start_permitted:
                self._pump_running = True
                self._last_start_t_s = t_s
                self._pump_starts += 1

        return ControlRequest(
            setpoint_m=setpoint_m,
            pump_run=self._pump_running,
            valve_position=self._valve_position(level),
            reserve_protection_active=self._reserve_protection_active,
        )

    def _valve_position(self, reported_level_m: float) -> float:
        """Determine the outlet valve command, applying reserve protection.

        When storage falls to the engage level the controller throttles the
        outlet, deliberately trading delivered service for reserve volume. It
        releases only above the higher release level, so the valve does not hunt.
        """
        protection = self._config.control.reserve_protection
        if self._reserve_protection_active:
            if reported_level_m >= protection.release_level_m:
                self._reserve_protection_active = False
        elif reported_level_m <= protection.engage_level_m:
            self._reserve_protection_active = True

        if self._reserve_protection_active:
            return protection.throttled_position
        return 1.0
