"""PLC scan abstraction.

A programmable controller does not run continuously; it executes a scan cycle at
a fixed interval and holds its outputs between scans. BLACKSTART integrates the
physics at 0.5 s while the controller scans at 1.0 s, so control action is
genuinely quantised in time and slightly stale with respect to the process.

This matters for the research question. A controller that reacted instantaneously
and continuously would mask the reaction-time component of every result, and
would make the tolerance windows on INV-002 and INV-003 meaningless.

The scanner deliberately holds outputs between scans rather than recomputing
them: holding last-known outputs across a scan boundary is what real controllers
do, and it is where reaction latency comes from.
"""

from __future__ import annotations

from blackstart.controller.control_logic import ControlRequest, LevelController
from blackstart.core.models import ReportedState

__all__ = ["PlcScanner"]

# Guards against float accumulation deciding a scan is due one step late.
_TIME_EPSILON_S = 1e-9


class PlcScanner:
    """Executes the control logic on a fixed scan interval, holding outputs between."""

    def __init__(self, controller: LevelController, scan_interval_s: float) -> None:
        """Bind the scanner to a controller and its scan interval.

        Raises:
            ValueError: if the scan interval is not positive.
        """
        if scan_interval_s <= 0.0:
            msg = f"scan_interval_s must be positive, got {scan_interval_s}"
            raise ValueError(msg)
        self._controller = controller
        self._scan_interval_s = scan_interval_s
        self._next_scan_t_s = 0.0
        self._held: ControlRequest | None = None
        self._scan_count = 0

    @property
    def controller(self) -> LevelController:
        """The control logic this scanner executes."""
        return self._controller

    @property
    def scan_count(self) -> int:
        """Number of control scans executed."""
        return self._scan_count

    def execute(self, reported: ReportedState, setpoint_m: float, t_s: float) -> ControlRequest:
        """Return the controller output for this timestep.

        Runs the control logic if a scan is due, otherwise returns the held
        output from the previous scan.
        """
        if self._held is None or t_s + _TIME_EPSILON_S >= self._next_scan_t_s:
            self._held = self._controller.scan(reported, setpoint_m, t_s)
            self._scan_count += 1
            self._next_scan_t_s = t_s + self._scan_interval_s
        elif self._held.setpoint_m != setpoint_m:
            # The held request still carries the previous scan's setpoint. Keep
            # the reported setpoint truthful without re-running control logic.
            self._held = ControlRequest(
                setpoint_m=setpoint_m,
                pump_run=self._held.pump_run,
                valve_position=self._held.valve_position,
                reserve_protection_active=self._held.reserve_protection_active,
            )
        return self._held
