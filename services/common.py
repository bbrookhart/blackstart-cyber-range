"""Shared helpers for the zoned demonstration services.

These services demonstrate the zone/conduit architecture (ADR-003). They are
**not** on the path of any published experimental result: experiments run in one
process through the CLI, so that nothing about network scheduling can enter the
causal path of the physics (ADR-001).

Every service follows the same shape: poll the next service inward on a fixed
interval, cache the most recent good sample, and serve it outward. Caching rather
than proxying is deliberate -- it means an inner service becoming unavailable
degrades the outer view to stale data instead of cascading a failure outward,
which is how a real historian/DMZ boundary behaves.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = ["ZONE_HEADER", "UpstreamPoller", "health_payload", "service_setting"]

#: Header naming the zone a response was served from. Purely diagnostic: it lets
#: a reviewer confirm by inspection which zone each hop came from.
ZONE_HEADER = "X-Blackstart-Zone"

_DEFAULT_TIMEOUT_S = 3.0


def service_setting(name: str, default: str) -> str:
    """Read a service setting from the environment.

    Configuration is by environment variable so the same image runs in every
    zone. No secrets are involved: these are hostnames and intervals.
    """
    return os.environ.get(name, default)


@dataclass
class UpstreamPoller:
    """Polls one upstream endpoint and caches its most recent good response."""

    url: str
    interval_s: float = 1.0
    #: Called with each newly fetched payload. Lets a service (the historian)
    #: archive samples without reaching into the poller's internals.
    on_sample: Callable[[dict[str, Any]], None] | None = None
    #: Most recent successful payload, or None if nothing has been fetched yet.
    latest: dict[str, Any] | None = None
    #: Polls that have failed since the last success.
    consecutive_failures: int = 0
    last_error: str | None = None
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    async def poll_once(self, client: httpx.AsyncClient) -> None:
        """Fetch the upstream endpoint once, recording success or failure."""
        try:
            response = await client.get(self.url, timeout=_DEFAULT_TIMEOUT_S)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Retain the last good sample: a stale view is more useful to an
            # operator than an empty one, provided its staleness is visible.
            self.consecutive_failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return

        self.latest = payload
        self.consecutive_failures = 0
        self.last_error = None
        if self.on_sample is not None:
            self.on_sample(payload)

    async def _loop(self) -> None:
        """Poll the upstream endpoint until cancelled."""
        async with httpx.AsyncClient() as client:
            while True:
                await self.poll_once(client)
                await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        """Begin polling in the background."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop polling and await task teardown."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def healthy(self) -> bool:
        """Whether a recent sample was obtained.

        A service that has never reached its upstream is unhealthy. One that has
        a cached sample and a small number of recent failures is degraded but
        serving, and reports healthy -- that distinction is the point of the
        cache.
        """
        return self.latest is not None and self.consecutive_failures < 5


def health_payload(
    service_id: str, zone: str, *, poller: UpstreamPoller | None = None, **extra: Any
) -> dict[str, Any]:
    """Build the standard health response for a service."""
    payload: dict[str, Any] = {
        "service": service_id,
        "zone": zone,
        "status": "ok",
        **extra,
    }
    if poller is not None:
        payload["upstream"] = {
            "url": poller.url,
            "healthy": poller.healthy,
            "consecutive_failures": poller.consecutive_failures,
            "last_error": poller.last_error,
        }
        if not poller.healthy:
            payload["status"] = "degraded"
    return payload
