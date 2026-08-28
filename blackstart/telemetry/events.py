"""Structured telemetry event model.

Every meaningful state change in a BLACKSTART experiment is emitted as an event
sharing one envelope. The envelope carries the zone the event originated in, so
an analysis can reason about which side of a trust boundary produced a given
observation.

Time is **simulation time in seconds**, not wall-clock time. Wall-clock values
appear only in the evidence manifest's provenance fields and are excluded from
the reproducibility hash (ADR-005); putting them in the event stream would
destroy byte-level reproducibility for no analytical gain.

The event model is intentionally free of any SIEM-specific structure. It is a
flat envelope plus a typed payload, which maps cleanly onto OpenTelemetry logs,
Elastic Common Schema, or a Splunk sourcetype without the core simulation
knowing that any of them exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["Event", "EventBus", "EventType", "Severity", "Zone"]


class Zone(StrEnum):
    """Security zone an event originated in (``configs/architecture.yaml``)."""

    ENTERPRISE = "enterprise"
    IDMZ = "idmz"
    OT = "ot"
    CONTROL = "control"
    #: The scenario engine and analysis layer sit outside the modelled plant.
    RANGE = "range"


class Severity(StrEnum):
    """Event severity, following common operational conventions."""

    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(StrEnum):
    """Closed set of event types emitted by v0.1.

    Kept closed so that downstream analysis can be exhaustive over the set, and
    so that adding a new observable is a deliberate, reviewed act.
    """

    PROCESS_TELEMETRY = "process.telemetry"
    CONTROL_COMMAND = "control.command"
    CONTROL_BACKSTOP = "control.backstop"
    OPERATOR_ACTION = "operator.action"
    INVARIANT_STATE = "invariant.state"
    SERVICE_STATE = "service.state"
    SCENARIO_EVENT = "scenario.event"
    CONSEQUENCE_CHANGE = "consequence.change"
    RECOVERY_ACTION = "recovery.action"
    EXPERIMENT_LIFECYCLE = "experiment.lifecycle"


@dataclass(frozen=True, slots=True)
class Event:
    """One structured telemetry event."""

    t_s: float
    experiment_id: str
    source: str
    zone: Zone
    event_type: EventType
    asset_id: str
    severity: Severity
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the JSON shape written to ``events.jsonl``."""
        return {
            "timestamp": round(self.t_s, 3),
            "t_s": round(self.t_s, 3),
            "experiment_id": self.experiment_id,
            "source": self.source,
            "zone": self.zone.value,
            "event_type": self.event_type.value,
            "asset_id": self.asset_id,
            "severity": self.severity.value,
            "data": self.data,
        }


class EventBus:
    """In-memory ordered event collector.

    Deliberately not a publish/subscribe system. Events are collected in
    deterministic emission order and written once at the end of a run, so the
    event stream is a function of the simulation alone and not of any consumer's
    behaviour.
    """

    def __init__(self) -> None:
        """Create an empty bus."""
        self._events: list[Event] = []

    def __len__(self) -> int:
        """Number of events collected."""
        return len(self._events)

    @property
    def events(self) -> tuple[Event, ...]:
        """All collected events, in emission order."""
        return tuple(self._events)

    def emit(self, event: Event) -> None:
        """Append an event to the stream."""
        self._events.append(event)

    def emit_many(self, events: list[Event]) -> None:
        """Append several events, preserving their order."""
        self._events.extend(events)

    def of_type(self, event_type: EventType) -> tuple[Event, ...]:
        """Return every collected event of one type."""
        return tuple(e for e in self._events if e.event_type is event_type)
