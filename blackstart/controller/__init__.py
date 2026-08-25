"""Control layer: control logic, PLC scan abstraction, engineering backstop.

The controller pursues its setpoint and is not a safety device. The backstop is
the safety-relevant component, and is deliberately independent of both the
controller and the invariant checker (ADR-004, ADR-006).
"""

from __future__ import annotations

from blackstart.controller.backstop import (
    BackstopDecision,
    EngineeringBackstop,
    SetpointConstraint,
)
from blackstart.controller.control_logic import ControlRequest, LevelController
from blackstart.controller.plc_sim import PlcScanner

__all__ = [
    "BackstopDecision",
    "ControlRequest",
    "EngineeringBackstop",
    "LevelController",
    "PlcScanner",
    "SetpointConstraint",
]
