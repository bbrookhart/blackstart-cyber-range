"""JSON Lines event exporter."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from blackstart.core.config import canonical_json
from blackstart.telemetry.events import Event

__all__ = ["write_events_jsonl"]


def write_events_jsonl(events: Iterable[Event], path: Path) -> int:
    """Write events to ``path`` as one canonical JSON object per line.

    Canonical serialisation (sorted keys, fixed separators) makes the file
    byte-identical across runs of the same experiment, which is what
    ``blackstart evidence verify`` relies on.

    Args:
        events: Events in emission order.
        path: Destination file. Parent directories must already exist.

    Returns:
        The number of events written.
    """
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(canonical_json(event.as_dict()))
            handle.write("\n")
            count += 1
    return count
