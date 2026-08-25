"""Controller service — control / process zone.

Runs a live instance of the BLACKSTART kernel: physics twin, hysteresis control,
and the engineering backstop. It is the innermost service and is attached only to
``blackstart_control``; nothing outside that network can reach it.

The backstop is enforced here, at the actuator, not at the API boundary. A
setpoint written through ``POST /setpoint`` is accepted, recorded, and then
constrained exactly as a setpoint from any other origin would be. That is the
architectural claim this service demonstrates: the constraint does not depend on
correctly identifying which commands are legitimate.

This service is a demonstration of the architecture. Published experimental
results come from the CLI, in one deterministic process (ADR-001).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from random import Random
from typing import Any

from blackstart import __version__
from blackstart.controller.backstop import EngineeringBackstop
from blackstart.controller.control_logic import LevelController
from blackstart.controller.plc_sim import PlcScanner
from blackstart.core.config import load_config
from blackstart.core.consequence.classifier import ConsequenceClassifier
from blackstart.core.invariants.engine import InvariantEngine
from blackstart.core.models import CommandState, ProcessState
from blackstart.core.physics.process import WaterProcessModel
from blackstart.core.physics.sensors import DemandModel, SensorModel
from fastapi import FastAPI
from pydantic import BaseModel, Field

from services.common import ZONE_HEADER, health_payload, service_setting

ZONE = "control"
SERVICE_ID = "controller"
#: Wall-clock seconds between simulation steps in the live demonstration.
_TICK_INTERVAL_S = 0.5


class SetpointRequest(BaseModel):
    """A supervisory setpoint write."""

    setpoint_m: float = Field(description="Requested tank level setpoint, metres.")
    origin: str = Field(default="hmi", description="Declared origin, recorded not trusted.")


class LiveProcess:
    """A continuously running instance of the simulation kernel."""

    def __init__(self) -> None:
        """Build the kernel from the shipped configuration."""
        self.config = load_config()
        process = self.config.process
        # Seeded for repeatable demonstration behaviour. This is a live view,
        # not an experiment; experiments run through the CLI.
        self._rng = Random(0)  # noqa: S311 - simulation variation, not cryptography
        self.physics = WaterProcessModel(process)
        self.sensors = SensorModel(process, self._rng)
        self.demand = DemandModel(process, self._rng)
        self.controller = LevelController(process)
        self.scanner = PlcScanner(self.controller, process.control.scan_interval_s)
        self.backstop = EngineeringBackstop(self.config.architecture.backstop, process)
        self.invariants = InvariantEngine(self.config.invariants, process)
        self.classifier = ConsequenceClassifier(self.config.consequences)

        self.truth = self.physics.initial_state()
        self.requested_setpoint_m = process.control.operator_setpoint_m
        self.t_s = 0.0
        self.last_command_origin = "startup"
        self.snapshot: dict[str, Any] = {}
        self._step()

    def _step(self) -> None:
        """Advance the live process by one timestep."""
        dt_s = self.config.process.simulation.timestep_s
        reported = self.sensors.read(self.truth)
        independent_level_m = self.sensors.read_independent_element(self.truth)
        demand_m3_s = self.demand.sample()

        constraint = self.backstop.constrain_setpoint(self.requested_setpoint_m, dt_s)
        request = self.scanner.execute(reported, constraint.effective_setpoint_m, self.t_s)
        decision = self.backstop.evaluate_permissive(
            request,
            constraint,
            independent_level_m=independent_level_m,
            source_level_m=self.truth.source_level_m,
            t_s=self.t_s,
        )
        if request.pump_run and not decision.pump_permitted:
            self.controller.notify_pump_denied(self.t_s)

        self.truth.pump_energised = decision.pump_permitted
        self.truth.valve_position = self.physics.slew_valve(
            self.truth.valve_position, decision.valve_position, dt_s
        )

        state = ProcessState(
            t_s=self.t_s,
            truth=self.truth,
            reported=reported,
            command=CommandState(
                requested_setpoint_m=self.requested_setpoint_m,
                effective_setpoint_m=decision.effective_setpoint_m,
                pump_permissive=decision.pump_permitted,
                pump_command=request.pump_run,
                valve_command=decision.valve_position,
                pump_starts=self.controller.pump_starts,
                backstop_actions=list(decision.constrained_by + decision.denied_by),
            ),
            independent_level_m=independent_level_m,
        )
        invariant_result = self.invariants.evaluate(state, dt_s)
        consequence = self.classifier.classify(state, invariant_result, dt_s)

        self.snapshot = {
            "t_s": round(self.t_s, 1),
            "true_tank_level_m": round(self.truth.tank_level_m, 4),
            "reported_tank_level_m": round(reported.tank_level_m, 4),
            "independent_level_m": round(independent_level_m, 4),
            "source_level_m": round(self.truth.source_level_m, 4),
            "inflow_m3_s": round(self.truth.inflow_m3_s, 6),
            "outflow_m3_s": round(self.truth.outflow_m3_s, 6),
            "demand_m3_s": round(self.truth.demand_m3_s, 6),
            "service_shortfall_ratio": round(self.truth.service_shortfall_ratio, 4),
            "pump_energised": self.truth.pump_energised,
            "pump_permitted": decision.pump_permitted,
            "valve_position": round(self.truth.valve_position, 4),
            "requested_setpoint_m": round(self.requested_setpoint_m, 4),
            "effective_setpoint_m": round(decision.effective_setpoint_m, 4),
            "backstop_enabled": self.backstop.enabled,
            "backstop_constrained_by": list(decision.constrained_by),
            "backstop_denied_by": list(decision.denied_by),
            "violated_invariants": sorted(invariant_result.violated_ids),
            "approaching_invariants": sorted(invariant_result.approaching_ids),
            "consequence_level": consequence.level.value,
            "consequence_drivers": list(consequence.drivers),
            "last_command_origin": self.last_command_origin,
            "supervisory_available": reported.supervisory_available,
        }

        self.physics.step(self.truth, demand_m3_s, dt_s)
        self.t_s += dt_s

    async def run(self) -> None:
        """Step the process on a wall-clock interval until cancelled."""
        while True:
            self._step()
            await asyncio.sleep(_TICK_INTERVAL_S)


def create_app() -> FastAPI:
    """Construct the controller service application."""
    live = LiveProcess()
    task: dict[str, asyncio.Task[None]] = {}

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task["run"] = asyncio.create_task(live.run())
        try:
            yield
        finally:
            task["run"].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task["run"]

    app = FastAPI(
        title="BLACKSTART Controller",
        description="PLC abstraction, engineering backstop and process twin.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.live = live

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness and process summary."""
        return health_payload(
            SERVICE_ID,
            ZONE,
            t_s=live.snapshot.get("t_s"),
            backstop_enabled=live.backstop.enabled,
            consequence_level=live.snapshot.get("consequence_level"),
        )

    @app.get("/state")
    def state() -> dict[str, Any]:
        """Current process state, as the control zone sees it."""
        return {"zone": ZONE, "source": SERVICE_ID, "state": live.snapshot}

    @app.post("/setpoint")
    def set_setpoint(request: SetpointRequest) -> dict[str, Any]:
        """Accept a supervisory setpoint write.

        The write is accepted and recorded. It is then subject to the
        engineering backstop exactly as any other setpoint would be -- the
        declared origin is recorded, never trusted, and never used to decide
        whether the constraint applies.
        """
        live.requested_setpoint_m = request.setpoint_m
        live.last_command_origin = request.origin
        constrained = live.backstop.constrain_setpoint(
            request.setpoint_m, live.config.process.simulation.timestep_s
        )
        return {
            "accepted": True,
            "requested_setpoint_m": request.setpoint_m,
            "effective_setpoint_m": round(constrained.effective_setpoint_m, 4),
            "constrained_by": list(constrained.constrained_by),
            "note": (
                "Acceptance is not authorisation. The effective setpoint is what "
                "the controller will pursue, after the engineering constraint."
            ),
        }

    @app.middleware("http")
    async def stamp_zone(request: Any, call_next: Any) -> Any:
        """Label every response with the zone that served it."""
        response = await call_next(request)
        response.headers[ZONE_HEADER] = ZONE
        return response

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        app,
        host=service_setting("BIND_HOST", "0.0.0.0"),  # noqa: S104 - container-internal only
        port=int(service_setting("PORT", "8084")),
    )
