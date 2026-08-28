"""Scenario-specific causal traces layered over the asset dependency graph."""

from __future__ import annotations

from typing import Any

from blackstart.scenario_engine.schema import Scenario

__all__ = ["scenario_consequence_graph"]


def scenario_consequence_graph(scenario: Scenario) -> dict[str, Any]:
    """Return the measured causal chain for a supported scenario.

    The graph is deliberately narrow. It represents only the state mutation the
    simulator actually performs; it does not invent an exploit chain or assert
    access techniques that BLACKSTART never executes.

    Non-flagship scenarios receive a minimal scenario/effect graph. Only
    SCN-004 has a claimed end-to-end mission-consequence path in v0.1.
    """
    if scenario.id != "SCN-004":
        nodes: list[dict[str, Any]] = [
            {"id": scenario.id, "class": "Scenario", "label": scenario.name}
        ]
        edges: list[dict[str, Any]] = []
        for index, event in enumerate(scenario.events, start=1):
            event_id = f"{scenario.id}-EVENT-{index:02d}"
            nodes.append({"id": event_id, "class": "ScenarioEvent", "label": event.effect})
            edges.append({"from": scenario.id, "to": event_id, "relation": "CONTAINS"})
        return {
            "scenario_id": scenario.id,
            "scenario_version": 1,
            "nodes": nodes,
            "edges": edges,
            "claim": "No end-to-end consequence path claimed for this scenario in v0.1.",
        }

    event = scenario.events[0]
    nodes = [
        {"id": scenario.id, "class": "CyberEvent", "label": scenario.name},
        {
            "id": "MUT-SETPOINT",
            "class": "ControlMutation",
            "label": event.effect,
        },
        {"id": "CTRL-LEVEL", "class": "ControlFunction", "label": "Level control"},
        {"id": "EBS-001", "class": "EngineeringBackstop", "label": "Engineering backstop"},
        {"id": "PMP-001", "class": "Actuator", "label": "Inlet pump"},
        {"id": "PROC-001", "class": "PhysicalProcess", "label": "Water storage process"},
        {"id": "INV-001", "class": "SafetyInvariant", "label": "Maximum safe level"},
        {"id": "C4", "class": "Consequence", "label": "Unsafe physical state"},
    ]
    edges = [
        {"from": scenario.id, "to": "MUT-SETPOINT", "relation": "CAN_CAUSE"},
        {"from": "MUT-SETPOINT", "to": "CTRL-LEVEL", "relation": "INFLUENCES"},
        {
            "from": "CTRL-LEVEL",
            "to": "EBS-001",
            "relation": "REQUESTS_ACTUATION_THROUGH",
        },
        {
            "from": "EBS-001",
            "to": "PMP-001",
            "relation": "PERMITS_OR_DENIES",
            "condition": "backstop enabled",
        },
        {
            "from": "CTRL-LEVEL",
            "to": "PMP-001",
            "relation": "CONTROLS",
            "condition": "backstop disabled",
        },
        {"from": "PMP-001", "to": "PROC-001", "relation": "AFFECTS"},
        {"from": "PROC-001", "to": "INV-001", "relation": "VIOLATES"},
        {"from": "INV-001", "to": "C4", "relation": "CAN_CAUSE"},
    ]
    return {
        "scenario_id": scenario.id,
        "scenario_version": 1,
        "event": {
            "effect": event.effect,
            "attack_time_s": event.t_s,
            "parameters": event.params,
        },
        "nodes": nodes,
        "edges": edges,
        "unprotected_path": [
            scenario.id,
            "MUT-SETPOINT",
            "CTRL-LEVEL",
            "PMP-001",
            "PROC-001",
            "INV-001",
            "C4",
        ],
        "protected_interruption": {
            "control": "EBS-001",
            "rule": "BS-01",
            "requested_value": event.params.get("value_m"),
            "result": "effective setpoint constrained before control action",
        },
    }
