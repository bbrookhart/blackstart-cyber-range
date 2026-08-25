"""Closed registry of scenario effects.

An effect is a bounded mutation of in-memory simulation state. The registry is
**closed**: :data:`EFFECT_REGISTRY` is the complete set, an unknown name is a
validation error, and ``tests/architecture/test_effect_registry.py`` asserts that
no effect outside the documented list exists.

What effects structurally cannot do
-----------------------------------
Effects have no access to sockets, subprocesses, environment variables, or the
filesystem. Neither this module nor anything in :mod:`blackstart.core` imports a
networking or process module, and a test walks the AST of both packages to keep
it that way. There is therefore no code path from a scenario file to any system
outside the Python process (ADR-006).

Effects are not exploits
------------------------
``setpoint.override`` writes to a field. It does not authenticate, bypass
authentication, craft a protocol frame, or exploit a flaw. It answers the
question "*given* that an adversary achieved unauthorised control influence,
which engineered constraint prevents that influence from becoming an
unacceptable physical consequence?"

This is deliberate scoping and also a real limitation: BLACKSTART cannot tell you
whether such influence is achievable against any particular system. It tells you
what happens if it is.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from blackstart.core.models import TruthState
from blackstart.core.physics.sensors import DemandModel, SensorModel

__all__ = [
    "EFFECT_REGISTRY",
    "Effect",
    "EffectContext",
    "SetpointHolder",
    "resolve_effect",
]


@dataclass(slots=True)
class SetpointHolder:
    """Mutable holder for the supervisory level setpoint.

    Separated from the controller so that a ``setpoint.override`` effect changes
    what the supervisory layer *holds*, exactly as an unauthorised control-state
    change would, without reaching into control logic.
    """

    requested_m: float


@dataclass(slots=True)
class EffectContext:
    """The simulation state an effect is permitted to touch.

    Deliberately narrow. An effect receives these four objects and nothing else
    -- no configuration writer, no filesystem handle, no runner reference.
    """

    demand: DemandModel
    sensors: SensorModel
    truth: TruthState
    setpoint: SetpointHolder


class Effect(ABC):
    """Base class for scenario effects."""

    #: Stable effect name used in scenario YAML.
    name: str = ""
    #: Human-readable statement of the condition being simulated.
    simulates: str = ""

    @abstractmethod
    def validate_params(self, params: dict[str, Any]) -> None:
        """Reject malformed parameters at scenario load time.

        Raises:
            ValueError: if required parameters are missing or out of range.
        """

    # activate/tick/deactivate are OPTIONAL hooks, deliberately concrete and
    # empty. Most effects implement only one of the three, and forcing every
    # effect to define all three would add empty overrides that obscure which
    # hook each effect actually uses.
    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:  # noqa: B027
        """Apply the effect. Called once, at the event's activation time."""

    def tick(  # noqa: B027
        self, ctx: EffectContext, params: dict[str, Any], elapsed_s: float, dt_s: float
    ) -> None:
        """Advance a time-varying effect. Called each timestep while active."""

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:  # noqa: B027
        """Revert the effect. Called once, when a bounded effect expires."""


def _require_number(params: dict[str, Any], key: str, effect: str) -> float:
    """Extract a required numeric parameter.

    Raises:
        ValueError: if the parameter is missing or not a number.
    """
    if key not in params:
        msg = f"effect '{effect}' requires parameter '{key}'"
        raise ValueError(msg)
    value = params[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        msg = f"effect '{effect}' parameter '{key}' must be numeric, got {value!r}"
        raise ValueError(msg)
    return float(value)


# ---------------------------------------------------------------------------
# Physical disturbances (benign). These are the control case: BLACKSTART must
# distinguish an ordinary load disturbance from a cyber-originated condition.
# ---------------------------------------------------------------------------


class DemandStepEffect(Effect):
    """Step change in downstream consumption."""

    name = "demand.step"
    simulates = "A benign step change in customer demand."

    def validate_params(self, params: dict[str, Any]) -> None:
        """Require a non-negative target rate."""
        rate = _require_number(params, "rate_m3_s", self.name)
        if rate < 0.0:
            msg = f"{self.name}: rate_m3_s must be non-negative"
            raise ValueError(msg)

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Set the base demand rate, remembering the previous value."""
        params["_previous_rate_m3_s"] = ctx.demand.base_rate_m3_s
        ctx.demand.base_rate_m3_s = float(params["rate_m3_s"])

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Restore the demand rate in force before activation."""
        previous = params.get("_previous_rate_m3_s")
        if previous is not None:
            ctx.demand.base_rate_m3_s = float(previous)


class DemandRampEffect(Effect):
    """Linear ramp of downstream consumption toward a target rate."""

    name = "demand.ramp"
    simulates = "A gradual, benign change in customer demand."

    def validate_params(self, params: dict[str, Any]) -> None:
        """Require a non-negative target and a positive ramp time."""
        target = _require_number(params, "target_m3_s", self.name)
        ramp_s = _require_number(params, "ramp_s", self.name)
        if target < 0.0:
            msg = f"{self.name}: target_m3_s must be non-negative"
            raise ValueError(msg)
        if ramp_s <= 0.0:
            msg = f"{self.name}: ramp_s must be positive"
            raise ValueError(msg)

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Record the starting rate the ramp interpolates from."""
        params["_start_rate_m3_s"] = ctx.demand.base_rate_m3_s

    def tick(
        self, ctx: EffectContext, params: dict[str, Any], elapsed_s: float, dt_s: float
    ) -> None:
        """Interpolate the demand rate along the ramp."""
        del dt_s
        start = float(params["_start_rate_m3_s"])
        target = float(params["target_m3_s"])
        ramp_s = float(params["ramp_s"])
        fraction = min(1.0, elapsed_s / ramp_s)
        ctx.demand.base_rate_m3_s = start + (target - start) * fraction


class SourceDepletionEffect(Effect):
    """Progressive depletion of the upstream source reservoir."""

    name = "source.depletion"
    simulates = "Drought, upstream failure, or supply diversion reducing available suction."

    def validate_params(self, params: dict[str, Any]) -> None:
        """Require a non-negative target level and a positive ramp time."""
        target = _require_number(params, "target_level_m", self.name)
        ramp_s = _require_number(params, "ramp_s", self.name)
        if target < 0.0:
            msg = f"{self.name}: target_level_m must be non-negative"
            raise ValueError(msg)
        if ramp_s <= 0.0:
            msg = f"{self.name}: ramp_s must be positive"
            raise ValueError(msg)

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Record the starting source level."""
        params["_start_level_m"] = ctx.truth.source_level_m

    def tick(
        self, ctx: EffectContext, params: dict[str, Any], elapsed_s: float, dt_s: float
    ) -> None:
        """Interpolate the source level along the depletion ramp."""
        del dt_s
        start = float(params["_start_level_m"])
        target = float(params["target_level_m"])
        ramp_s = float(params["ramp_s"])
        fraction = min(1.0, elapsed_s / ramp_s)
        ctx.truth.source_level_m = start + (target - start) * fraction


# ---------------------------------------------------------------------------
# Telemetry-integrity effects. These change what is REPORTED. They never touch
# TruthState, which is why the evidence record survives them.
# ---------------------------------------------------------------------------


class SensorBiasEffect(Effect):
    """Constant offset applied to the reported tank level."""

    name = "sensor.bias"
    simulates = "A level transmitter reporting a consistent, plausible, wrong value."

    def validate_params(self, params: dict[str, Any]) -> None:
        """Require a numeric bias."""
        _require_number(params, "bias_m", self.name)

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Apply the reporting bias."""
        ctx.sensors.fault_level_bias_m = float(params["bias_m"])

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Remove the reporting bias."""
        del params
        ctx.sensors.fault_level_bias_m = 0.0


class SensorFreezeEffect(Effect):
    """The level transmitter holds its last reported value."""

    name = "sensor.freeze"
    simulates = "A transmitter whose trend looks stable and plausible while the process moves."

    def validate_params(self, params: dict[str, Any]) -> None:
        """No parameters are required."""

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Freeze the reported level."""
        del params
        ctx.sensors.fault_level_frozen = True

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Resume live reporting."""
        del params
        ctx.sensors.fault_level_frozen = False


class SupervisoryBlackoutEffect(Effect):
    """Supervisory telemetry path becomes unavailable."""

    name = "supervisory.blackout"
    simulates = (
        "Loss of the operator's view of the process while local control continues. "
        "Loss of view is not loss of control, and SCN-005 exists to measure the difference."
    )

    def validate_params(self, params: dict[str, Any]) -> None:
        """No parameters are required."""

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Mark the supervisory path unavailable."""
        del params
        ctx.sensors.fault_supervisory_available = False

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Restore the supervisory path."""
        del params
        ctx.sensors.fault_supervisory_available = True


# ---------------------------------------------------------------------------
# Control-state effects.
# ---------------------------------------------------------------------------


class SetpointOverrideEffect(Effect):
    """Unauthorised mutation of the supervisory level setpoint.

    Stands in for a control-state change of unauthorised origin. It writes a
    field; it does not authenticate, bypass authentication, or exploit anything.
    """

    name = "setpoint.override"
    simulates = "A level setpoint changed by something other than legitimate operator action."

    def validate_params(self, params: dict[str, Any]) -> None:
        """Require a non-negative target setpoint."""
        value = _require_number(params, "value_m", self.name)
        if value < 0.0:
            msg = f"{self.name}: value_m must be non-negative"
            raise ValueError(msg)

    def activate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Mutate the held setpoint, remembering the legitimate value."""
        params["_previous_setpoint_m"] = ctx.setpoint.requested_m
        ctx.setpoint.requested_m = float(params["value_m"])

    def deactivate(self, ctx: EffectContext, params: dict[str, Any]) -> None:
        """Restore the setpoint in force before the override."""
        previous = params.get("_previous_setpoint_m")
        if previous is not None:
            ctx.setpoint.requested_m = float(previous)


#: The complete effect vocabulary. Closed by design; see ADR-006.
EFFECT_REGISTRY: dict[str, Effect] = {
    effect.name: effect
    for effect in (
        DemandStepEffect(),
        DemandRampEffect(),
        SourceDepletionEffect(),
        SensorBiasEffect(),
        SensorFreezeEffect(),
        SupervisoryBlackoutEffect(),
        SetpointOverrideEffect(),
    )
}


def resolve_effect(name: str) -> Effect:
    """Look up an effect by name.

    Args:
        name: Effect name from a scenario event.

    Returns:
        The registered effect instance.

    Raises:
        ValueError: if the name is not in the closed registry. This is the load-
            time failure that keeps the effect vocabulary bounded.
    """
    effect = EFFECT_REGISTRY.get(name)
    if effect is None:
        known = ", ".join(sorted(EFFECT_REGISTRY))
        msg = f"unknown scenario effect '{name}'; the registry is closed. Known effects: {known}"
        raise ValueError(msg)
    return effect
