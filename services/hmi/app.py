"""HMI service — OT supervisory zone.

The operator's view of the process, and the only service permitted to originate
a control command. It bridges ``blackstart_ot`` and ``blackstart_control``, which
makes it the single conduit CDT-004 (ADR-003).

The view it serves is built from what the controller *reports*. When telemetry
integrity is lost, this service shows the wrong thing -- faithfully. An HMI that
displayed ground truth would be a modelling error: it is precisely the operator's
dependence on reported state that gives loss of telemetry integrity its
significance.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import httpx
from blackstart import __version__
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.common import ZONE_HEADER, UpstreamPoller, health_payload, service_setting

ZONE = "ot"
SERVICE_ID = "hmi"


class SetpointRequest(BaseModel):
    """An operator setpoint change."""

    setpoint_m: float = Field(description="Requested tank level setpoint, metres.")


def create_app(controller_url: str | None = None) -> FastAPI:
    """Construct the HMI service application."""
    base = controller_url or service_setting("CONTROLLER_URL", "http://controller:8084")
    poller = UpstreamPoller(url=f"{base}/state", interval_s=1.0)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        poller.start()
        try:
            yield
        finally:
            await poller.stop()

    app = FastAPI(
        title="BLACKSTART HMI",
        description="Operator process view (OT supervisory zone).",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.poller = poller

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness and upstream conduit status."""
        return health_payload(SERVICE_ID, ZONE, poller=poller)

    @app.get("/view")
    def view() -> dict[str, Any]:
        """The operator-facing process view.

        Reports what the instrumentation says, including whether that view is
        currently stale.
        """
        if poller.latest is None:
            raise HTTPException(status_code=503, detail="No controller sample yet.")
        state = poller.latest.get("state", {})
        return {
            "zone": ZONE,
            "source": SERVICE_ID,
            "conduit": "CDT-004",
            "stale": not poller.healthy,
            "view": {
                "tank_level_m": state.get("reported_tank_level_m"),
                "setpoint_m": state.get("effective_setpoint_m"),
                "requested_setpoint_m": state.get("requested_setpoint_m"),
                "pump_running": state.get("pump_energised"),
                "valve_position": state.get("valve_position"),
                "demand_m3_s": state.get("demand_m3_s"),
                "service_shortfall_ratio": state.get("service_shortfall_ratio"),
                "consequence_level": state.get("consequence_level"),
                "violated_invariants": state.get("violated_invariants", []),
                "approaching_invariants": state.get("approaching_invariants", []),
                "backstop_enabled": state.get("backstop_enabled"),
                "backstop_active_rules": (
                    list(state.get("backstop_constrained_by", []))
                    + list(state.get("backstop_denied_by", []))
                ),
                "t_s": state.get("t_s"),
            },
        }

    @app.post("/setpoint")
    async def set_setpoint(request: SetpointRequest) -> dict[str, Any]:
        """Forward an operator setpoint change to the controller over CDT-004."""
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.post(
                    f"{base}/setpoint",
                    json={"setpoint_m": request.setpoint_m, "origin": "hmi-operator"},
                    timeout=3.0,
                )
                response.raise_for_status()
                return dict(response.json())
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Controller unreachable: {exc}") from exc

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
        port=int(service_setting("PORT", "8083")),
    )
