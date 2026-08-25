"""Report the health of every service in the deployed topology.

Health is read from the Docker health-check state rather than by connecting to
each service, because only one service is reachable from the host by design
(ADR-003). Probing the inner services from here would require exactly the
host-to-OT reachability the architecture exists to prevent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Services expected in a healthy topology, innermost first.
EXPECTED_SERVICES = (
    "controller",
    "hmi",
    "historian",
    "idmz-broker",
    "enterprise-workstation",
)

_HEALTHY = "healthy"


def _compose_ps() -> list[dict[str, Any]]:
    """Return the Compose service table.

    Raises:
        RuntimeError: if Docker is unavailable or the command fails.
    """
    if shutil.which("docker") is None:
        msg = "docker is not installed or not on PATH"
        raise RuntimeError(msg)

    try:
        completed = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"could not run 'docker compose ps': {exc}"
        raise RuntimeError(msg) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        msg = f"'docker compose ps' failed: {detail}"
        raise RuntimeError(msg)

    # Compose emits either a JSON array or newline-delimited objects depending
    # on version; accept both rather than pinning to one.
    text = completed.stdout.strip()
    if not text:
        return []
    if text.startswith("["):
        parsed = json.loads(text)
        return list(parsed) if isinstance(parsed, list) else []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main() -> int:
    """Print a health table and return a process exit status."""
    try:
        rows = _compose_ps()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("\nStart the topology first:  make up", file=sys.stderr)
        return 2

    if not rows:
        print("No BLACKSTART containers are running.")
        print("Start the topology first:  make up")
        return 1

    by_service = {row.get("Service"): row for row in rows}
    print(f"{'SERVICE':<24} {'STATE':<12} {'HEALTH':<12} PORTS")

    all_healthy = True
    for name in EXPECTED_SERVICES:
        row = by_service.get(name)
        if row is None:
            print(f"{name:<24} {'absent':<12} {'-':<12} -")
            all_healthy = False
            continue
        state = str(row.get("State", "?"))
        health = str(row.get("Health") or "none")
        ports = str(row.get("Publishers") or row.get("Ports") or "-")
        if isinstance(row.get("Publishers"), list):
            published = [
                f"{p.get('URL', '')}:{p.get('PublishedPort')}->{p.get('TargetPort')}"
                for p in row["Publishers"]
                if p.get("PublishedPort")
            ]
            ports = ", ".join(published) or "-"
        print(f"{name:<24} {state:<12} {health:<12} {ports}")
        if health != _HEALTHY:
            all_healthy = False

    unexpected = sorted(set(by_service) - set(EXPECTED_SERVICES) - {None})
    for name in unexpected:
        print(f"{name!s:<24} {'UNEXPECTED':<12}")
        all_healthy = False

    print("")
    if all_healthy:
        print("All services healthy.")
        print("Enterprise dashboard: http://127.0.0.1:8080/  (loopback only)")
        return 0
    print("One or more services are not healthy.")
    print("Inspect with:  docker compose logs --tail 50")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
