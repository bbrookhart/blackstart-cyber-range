"""Structured telemetry: event envelope, bus, and evidence exporters.

The core simulation is not coupled to any SIEM or observability backend. Events
carry a flat envelope plus a typed payload, which maps onto OpenTelemetry logs,
Elastic Common Schema or a Splunk sourcetype downstream without the physics
engine knowing any of them exist.
"""

from __future__ import annotations

from blackstart.telemetry.events import Event, EventBus, EventType, Severity, Zone

__all__ = ["Event", "EventBus", "EventType", "Severity", "Zone"]
