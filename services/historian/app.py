"""Historian service — OT supervisory zone.

Archives the operator view on a fixed interval and serves it outward to the
industrial DMZ. It bridges ``blackstart_idmz`` and ``blackstart_ot``, forming
conduit CDT-002.

The historian is read-only in the outward direction. Nothing it serves can become
a command, which is why the enterprise zone can be given a view of the process
without being given influence over it.
"""

from __future__ import annotations

import contextlib
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from blackstart import __version__
from fastapi import FastAPI, Query

from services.common import ZONE_HEADER, UpstreamPoller, health_payload, service_setting

ZONE = "ot"
SERVICE_ID = "historian"
#: Ring-buffer depth. Bounded so the demonstration cannot grow without limit.
_MAX_SAMPLES = 2000


def create_app(hmi_url: str | None = None) -> FastAPI:
    """Construct the historian service application."""
    base = hmi_url or service_setting("HMI_URL", "http://hmi:8083")
    samples: deque[dict[str, Any]] = deque(maxlen=_MAX_SAMPLES)

    def archive(payload: dict[str, Any]) -> None:
        """Append a newly polled view to the archive, de-duplicating by timestep."""
        view = payload.get("view", {})
        if not samples or samples[-1].get("t_s") != view.get("t_s"):
            samples.append(dict(view))

    poller = UpstreamPoller(url=f"{base}/view", interval_s=1.0, on_sample=archive)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        poller.start()
        try:
            yield
        finally:
            await poller.stop()

    app = FastAPI(
        title="BLACKSTART Historian",
        description="Process telemetry archive (OT supervisory zone).",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.poller = poller
    app.state.samples = samples

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness, upstream conduit status and archive depth."""
        return health_payload(SERVICE_ID, ZONE, poller=poller, samples=len(samples))

    @app.get("/query")
    def query(limit: int = Query(default=60, ge=1, le=_MAX_SAMPLES)) -> dict[str, Any]:
        """Return the most recent archived samples, newest last."""
        window = list(samples)[-limit:]
        return {
            "zone": ZONE,
            "source": SERVICE_ID,
            "conduit": "CDT-003",
            "count": len(window),
            "samples": window,
            "latest": window[-1] if window else None,
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
        port=int(service_setting("PORT", "8082")),
    )
