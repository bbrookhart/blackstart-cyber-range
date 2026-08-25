"""Industrial DMZ broker — industrial DMZ zone.

The only service attached to both ``blackstart_enterprise`` and
``blackstart_idmz``. Every flow between enterprise IT and the OT side traverses
this process, and there is no alternative route (ADR-003).

The broker deliberately narrows what it passes outward. It receives full
historian samples and serves a reduced summary: a handful of process values and
status flags. Narrowing at the boundary rather than forwarding wholesale is the
point of a DMZ broker -- the enterprise zone receives what it needs to report,
not a general-purpose window into OT.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from blackstart import __version__
from fastapi import FastAPI, HTTPException

from services.common import ZONE_HEADER, UpstreamPoller, health_payload, service_setting

ZONE = "idmz"
SERVICE_ID = "idmz-broker"

#: Fields the broker is permitted to pass outward. Anything not named here does
#: not cross the boundary, including the setpoint and any command detail.
_PERMITTED_FIELDS = (
    "t_s",
    "tank_level_m",
    "pump_running",
    "service_shortfall_ratio",
    "consequence_level",
    "violated_invariants",
)


def create_app(historian_url: str | None = None) -> FastAPI:
    """Construct the industrial DMZ broker application."""
    base = historian_url or service_setting("HISTORIAN_URL", "http://historian:8082")
    poller = UpstreamPoller(url=f"{base}/query?limit=30", interval_s=2.0)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        poller.start()
        try:
            yield
        finally:
            await poller.stop()

    app = FastAPI(
        title="BLACKSTART Industrial DMZ Broker",
        description="Brokered, read-only telemetry boundary between enterprise IT and OT.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.poller = poller

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness and upstream conduit status."""
        return health_payload(SERVICE_ID, ZONE, poller=poller)

    @app.get("/summary")
    def summary() -> dict[str, Any]:
        """A reduced, read-only process summary for the enterprise zone."""
        if poller.latest is None:
            raise HTTPException(status_code=503, detail="No historian sample yet.")
        latest = poller.latest.get("latest") or {}
        reduced = {field: latest.get(field) for field in _PERMITTED_FIELDS}
        return {
            "zone": ZONE,
            "source": SERVICE_ID,
            "conduit": "CDT-002",
            "stale": not poller.healthy,
            "sample_count": poller.latest.get("count", 0),
            "summary": reduced,
            "note": (
                "Read-only. This boundary passes a fixed set of process values "
                "outward and carries no command path inward."
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
        port=int(service_setting("PORT", "8081")),
    )
