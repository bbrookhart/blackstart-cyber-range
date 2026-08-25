"""Enterprise reporting workstation — enterprise zone.

The outermost service and the **only** one published to the host, on
``127.0.0.1:8080``. It is attached solely to ``blackstart_enterprise`` and cannot
reach the historian, the HMI, or the controller; everything it shows arrived
through the DMZ broker.

This service exists so that the demonstration does not require publishing a
supervisory-zone service to the host. Exposing the HMI directly would have been
more convenient and would have contradicted the architecture the project is
arguing for.
"""

from __future__ import annotations

import contextlib
import html
from collections.abc import AsyncIterator
from typing import Any

from blackstart import __version__
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from services.common import ZONE_HEADER, UpstreamPoller, health_payload, service_setting

ZONE = "enterprise"
SERVICE_ID = "enterprise-workstation"


def create_app(broker_url: str | None = None) -> FastAPI:
    """Construct the enterprise reporting workstation application."""
    base = broker_url or service_setting("BROKER_URL", "http://idmz-broker:8081")
    poller = UpstreamPoller(url=f"{base}/summary", interval_s=2.0)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        poller.start()
        try:
            yield
        finally:
            await poller.stop()

    app = FastAPI(
        title="BLACKSTART Enterprise Dashboard",
        description="Read-only operational reporting (enterprise zone).",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.poller = poller

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Liveness and upstream conduit status."""
        return health_payload(SERVICE_ID, ZONE, poller=poller)

    @app.get("/api/summary")
    def api_summary() -> dict[str, Any]:
        """The process summary as received through the DMZ broker."""
        return {
            "zone": ZONE,
            "source": SERVICE_ID,
            "conduit": "CDT-001",
            "stale": not poller.healthy,
            "upstream": poller.latest,
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        """A minimal read-only dashboard.

        Values are escaped before rendering. They originate three zones inward
        and are treated as untrusted data at this boundary, which is the same
        discipline the architecture argues for everywhere else.
        """
        upstream = poller.latest or {}
        summary: dict[str, Any] = upstream.get("summary", {}) if upstream else {}
        rows = (
            "".join(
                f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
                for key, value in summary.items()
            )
            or "<tr><td colspan='2'>Awaiting first sample from the industrial DMZ.</td></tr>"
        )

        status = "stale" if not poller.healthy else "live"
        return HTMLResponse(
            f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>BLACKSTART — Enterprise Reporting</title>
<meta http-equiv="refresh" content="5">
<style>
 body{{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
      background:#0f1216;color:#d7dee7;margin:0;padding:2rem}}
 h1{{font-size:1.1rem;letter-spacing:.18em;color:#e8eef5;margin:0 0 .25rem}}
 .sub{{color:#7d8b9a;margin:0 0 1.5rem}}
 table{{border-collapse:collapse;min-width:min(30rem,100%)}}
 th,td{{text-align:left;padding:.4rem .9rem;border-bottom:1px solid #232a33}}
 th{{color:#8fa3b8;font-weight:400}}
 .tag{{display:inline-block;padding:.1rem .5rem;border:1px solid #2f3945;
       border-radius:3px;color:#8fa3b8;font-size:.75rem}}
 .path{{color:#5d6b7a;font-size:.75rem;margin-top:1.5rem}}
</style></head><body>
<h1>BLACKSTART</h1>
<p class="sub">Enterprise reporting &mdash; read-only
 <span class="tag">zone: enterprise</span> <span class="tag">{status}</span></p>
<table>{rows}</table>
<p class="path">Data path: controller (control) &rarr; hmi (ot) &rarr;
 historian (ot) &rarr; idmz-broker (idmz) &rarr; this service (enterprise).
 No command path exists in the reverse direction from this zone.</p>
</body></html>""",
            headers={ZONE_HEADER: ZONE},
        )

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
        port=int(service_setting("PORT", "8080")),
    )
