"""Consequence dependency graph construction.

The graph is a NetworkX ``MultiDiGraph`` whose edges point in the direction of
**causal influence**: an edge ``A -> B`` means a change in ``A`` can produce a
change in ``B``. That orientation is what lets a path query answer the question
the project actually cares about -- which digital components can influence which
physical outcomes -- rather than merely describing data flow.

A lightweight in-memory graph is deliberate. A graph database would add
operational surface and a service dependency for a model of roughly thirty nodes
that is rebuilt from configuration in milliseconds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import networkx as nx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from blackstart.core.config import (
    DEFAULT_CONFIG_DIR,
    ConsequencesConfig,
    InvariantsConfig,
)

__all__ = [
    "EDGE_RELATIONS",
    "INFLUENCE_RELATIONS",
    "NODE_CLASSES",
    "AssetModel",
    "ConsequenceGraph",
    "build_graph",
    "load_asset_model",
]

#: Node classes represented in the dependency model.
NODE_CLASSES: frozenset[str] = frozenset(
    {
        "CriticalFunction",
        "PhysicalProcess",
        "Asset",
        "Service",
        "Identity",
        "Sensor",
        "Actuator",
        "ControlFunction",
        "SafetyInvariant",
        "Consequence",
    }
)

#: Relations represented in the dependency model.
EDGE_RELATIONS: frozenset[str] = frozenset(
    {
        "DEPENDS_ON",
        "CONTROLS",
        "OBSERVES",
        "COMMUNICATES_WITH",
        "ENABLES",
        "PROTECTS",
        "CAN_CAUSE",
        "VIOLATES",
    }
)

#: Relations along which influence propagates. ``DEPENDS_ON`` and ``PROTECTS``
#: are excluded: a dependency edge points from dependent to dependency, which is
#: the opposite of the influence direction, and a protection edge describes a
#: control rather than a causal step.
INFLUENCE_RELATIONS: frozenset[str] = frozenset(
    {"CONTROLS", "OBSERVES", "COMMUNICATES_WITH", "ENABLES", "CAN_CAUSE", "VIOLATES"}
)


class _Frozen(BaseModel):
    """Immutable, strictly validated asset-model element."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class NodeSpec(_Frozen):
    """One node in the dependency model."""

    id: str
    node_class: str
    label: str
    zone: str

    @model_validator(mode="after")
    def _known_class(self) -> Self:
        if self.node_class not in NODE_CLASSES:
            msg = f"node {self.id}: unknown node_class {self.node_class!r}"
            raise ValueError(msg)
        return self


class EdgeSpec(_Frozen):
    """One directed influence edge in the dependency model."""

    from_: str = Field(alias="from")
    to: str
    relation: str
    note: str | None = None
    #: Backstop rule identifiers that break this edge.
    interrupted_by: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _known_relation(self) -> Self:
        if self.relation not in EDGE_RELATIONS:
            msg = f"edge {self.from_}->{self.to}: unknown relation {self.relation!r}"
            raise ValueError(msg)
        return self


class AssetModel(_Frozen):
    """The declarative asset and dependency model (``configs/assets.yaml``)."""

    schema_version: int
    nodes: list[NodeSpec] = Field(min_length=1)
    edges: list[EdgeSpec] = Field(min_length=1)
    invariant_consequences: dict[str, str]

    @model_validator(mode="after")
    def _node_ids_unique(self) -> Self:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            msg = f"duplicate node ids in asset model: {ids}"
            raise ValueError(msg)
        return self


def load_asset_model(config_dir: Path | None = None) -> AssetModel:
    """Load the asset and dependency model from configuration.

    Raises:
        FileNotFoundError: if ``assets.yaml`` is missing.
        ValueError: if the document is not a mapping.
    """
    directory = config_dir if config_dir is not None else DEFAULT_CONFIG_DIR
    path = directory / "assets.yaml"
    if not path.is_file():
        msg = f"asset model not found: {path}"
        raise FileNotFoundError(msg)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        msg = f"expected a YAML mapping at the top level of {path}"
        raise ValueError(msg)
    return AssetModel.model_validate(document)


class ConsequenceGraph:
    """Queryable dependency graph over the modelled system of systems."""

    def __init__(self, graph: nx.MultiDiGraph, asset_model: AssetModel) -> None:
        """Wrap a constructed graph with its source model."""
        self._graph = graph
        self._model = asset_model

    @property
    def graph(self) -> nx.MultiDiGraph:
        """The underlying NetworkX graph."""
        return self._graph

    @property
    def node_count(self) -> int:
        """Number of nodes in the model."""
        return int(self._graph.number_of_nodes())

    @property
    def edge_count(self) -> int:
        """Number of edges in the model."""
        return int(self._graph.number_of_edges())

    def nodes_of_class(self, node_class: str) -> list[str]:
        """Identifiers of every node of a given class, sorted."""
        return sorted(
            node
            for node, data in self._graph.nodes(data=True)
            if data.get("node_class") == node_class
        )

    def label(self, node_id: str) -> str:
        """Human-readable label for a node."""
        data: dict[str, Any] = self._graph.nodes[node_id]
        label = data.get("label", node_id)
        return str(label)


def build_graph(
    asset_model: AssetModel,
    invariants: InvariantsConfig,
    consequences: ConsequencesConfig,
) -> ConsequenceGraph:
    """Construct the consequence dependency graph.

    Safety invariants and consequence classes are added from their own
    configuration rather than duplicated in the asset model, and the
    ``invariant -> consequence`` edges are generated from
    ``severity_on_violation``. That way the graph cannot disagree with the
    invariant definitions the simulation actually runs.

    Args:
        asset_model: Declarative nodes and edges.
        invariants: Invariant configuration, contributing SafetyInvariant nodes.
        consequences: Consequence taxonomy, contributing Consequence nodes.

    Returns:
        The queryable graph.

    Raises:
        ValueError: if an edge references an unknown node, or if the asset
            model's invariant/consequence mapping contradicts the invariant
            configuration.
    """
    graph = nx.MultiDiGraph()

    for node in asset_model.nodes:
        graph.add_node(node.id, node_class=node.node_class, label=node.label, zone=node.zone)

    for spec in invariants.invariants:
        graph.add_node(
            spec.id,
            node_class="SafetyInvariant",
            label=spec.name,
            zone="range",
            severity_on_violation=spec.severity_on_violation,
        )

    for consequence in consequences.consequences:
        graph.add_node(
            consequence.level,
            node_class="Consequence",
            label=consequence.name,
            zone="range",
            rank=int(consequence.level[1]),
        )

    for edge in asset_model.edges:
        for endpoint in (edge.from_, edge.to):
            if endpoint not in graph:
                msg = (
                    f"edge {edge.from_}->{edge.to} references unknown node "
                    f"{endpoint!r}; the asset model and invariant configuration "
                    f"have drifted apart"
                )
                raise ValueError(msg)
        graph.add_edge(
            edge.from_,
            edge.to,
            relation=edge.relation,
            note=edge.note,
            interrupted_by=tuple(edge.interrupted_by),
        )

    # Invariant -> consequence edges, generated from severity_on_violation so the
    # graph and the running invariants cannot disagree.
    for spec in invariants.invariants:
        declared = asset_model.invariant_consequences.get(spec.id)
        if declared is not None and declared != spec.severity_on_violation:
            msg = (
                f"asset model maps {spec.id} to {declared}, but invariants.yaml "
                f"declares severity_on_violation={spec.severity_on_violation}"
            )
            raise ValueError(msg)
        graph.add_edge(
            spec.id,
            spec.severity_on_violation,
            relation="CAN_CAUSE",
            note="Generated from invariants.yaml severity_on_violation.",
            interrupted_by=(),
        )

    return ConsequenceGraph(graph, asset_model)
