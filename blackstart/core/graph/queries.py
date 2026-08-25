"""Dependency-graph queries.

These answer the system-of-systems questions a consequence-driven analysis asks:

- What supports the critical function?
- Which digital components can influence a given safety invariant?
- Which dependency paths terminate in a high-consequence outcome?
- Which engineering control interrupts a given path, and how many paths does it
  remove?

The last question yields the consequence-path-reduction metric, which is a
property of the *architecture* rather than of any single experiment. It is
reported alongside experimental results and clearly labelled as such: a path is
a modelled possibility, not an observed event.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import networkx as nx

from blackstart.core.graph.build import INFLUENCE_RELATIONS, ConsequenceGraph

__all__ = [
    "ConsequencePath",
    "PathReduction",
    "components_influencing",
    "consequence_paths",
    "path_reduction",
    "supporting_assets",
]

# Bounds enumeration on a small hand-built graph. The shipped model produces far
# fewer paths than this; the cap exists so a future model edit cannot turn a
# query into a hang.
_MAX_PATH_LENGTH = 12


@dataclass(frozen=True, slots=True)
class ConsequencePath:
    """One dependency path terminating in a consequence class."""

    nodes: tuple[str, ...]
    terminal_consequence: str
    #: Backstop rules that break at least one edge on this path.
    interrupted_by: frozenset[str]

    @property
    def is_interrupted(self) -> bool:
        """Whether an engineering control breaks this path."""
        return bool(self.interrupted_by)

    @property
    def origin(self) -> str:
        """The node the path starts from."""
        return self.nodes[0]

    def as_dict(self) -> dict[str, Any]:
        """Serialise for reporting and for ``threat-model/consequence-paths.yaml``."""
        return {
            "path": list(self.nodes),
            "terminal_consequence": self.terminal_consequence,
            "interrupted_by": sorted(self.interrupted_by),
            "is_interrupted": self.is_interrupted,
        }

    def render(self) -> str:
        """Render the path as an arrow chain."""
        return " -> ".join(self.nodes)


def _influence_view(graph: nx.MultiDiGraph) -> nx.DiGraph:
    """Project the multigraph onto a simple digraph of influence edges.

    Parallel edges are collapsed, and the union of their ``interrupted_by`` rule
    sets is carried onto the collapsed edge. Collapsing is safe here because path
    *existence* is what the queries ask about; the relation label is retained for
    reporting.
    """
    view = nx.DiGraph()
    view.add_nodes_from(graph.nodes(data=True))
    for source, target, data in graph.edges(data=True):
        if data.get("relation") not in INFLUENCE_RELATIONS:
            continue
        interrupted = set(data.get("interrupted_by", ()))
        if view.has_edge(source, target):
            view[source][target]["interrupted_by"] |= interrupted
        else:
            view.add_edge(
                source,
                target,
                relation=data.get("relation"),
                interrupted_by=interrupted,
            )
    return view


def supporting_assets(cgraph: ConsequenceGraph, critical_function_id: str) -> list[str]:
    """Return every asset the critical function directly or indirectly depends on.

    Follows ``DEPENDS_ON`` edges transitively from the critical function, then
    adds everything that can influence those dependencies. The result answers
    "what would I have to protect to protect CF-001?"

    Raises:
        KeyError: if the critical function is not in the model.
    """
    graph = cgraph.graph
    if critical_function_id not in graph:
        msg = f"unknown critical function: {critical_function_id}"
        raise KeyError(msg)

    direct: set[str] = set()
    frontier = [critical_function_id]
    while frontier:
        node = frontier.pop()
        for _, target, data in graph.out_edges(node, data=True):
            if data.get("relation") == "DEPENDS_ON" and target not in direct:
                direct.add(target)
                frontier.append(target)

    influence = _influence_view(graph)
    supporting: set[str] = set(direct)
    for dependency in direct:
        supporting |= nx.ancestors(influence, dependency)

    supporting.discard(critical_function_id)
    return sorted(supporting)


def components_influencing(cgraph: ConsequenceGraph, invariant_id: str) -> list[str]:
    """Return every component that can influence a given safety invariant.

    Raises:
        KeyError: if the invariant is not in the model.
    """
    graph = cgraph.graph
    if invariant_id not in graph:
        msg = f"unknown invariant: {invariant_id}"
        raise KeyError(msg)
    return sorted(nx.ancestors(_influence_view(graph), invariant_id))


def consequence_paths(
    cgraph: ConsequenceGraph,
    *,
    minimum_class: str = "C4",
    origin_classes: frozenset[str] | None = None,
) -> list[ConsequencePath]:
    """Enumerate dependency paths terminating in a high-consequence outcome.

    Args:
        cgraph: The dependency graph.
        minimum_class: Lowest consequence class of interest, e.g. ``"C4"``.
        origin_classes: Node classes treated as path origins. Defaults to the
            digital and identity components an adversary might influence --
            physical assets are excluded because BLACKSTART studies cyber-
            originated consequence, not equipment failure.

    Returns:
        Paths sorted by terminal consequence (descending), then by length.
    """
    origins = (
        origin_classes
        if origin_classes is not None
        else frozenset({"Service", "Identity", "Sensor", "ControlFunction", "Asset"})
    )
    graph = cgraph.graph
    influence = _influence_view(graph)
    minimum_rank = int(minimum_class[1])

    targets = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("node_class") == "Consequence" and int(data.get("rank", 0)) >= minimum_rank
    ]
    sources = [node for node, data in graph.nodes(data=True) if data.get("node_class") in origins]

    found: list[ConsequencePath] = []
    for source in sources:
        for target in targets:
            if source == target or not nx.has_path(influence, source, target):
                continue
            for path in nx.all_simple_paths(influence, source, target, cutoff=_MAX_PATH_LENGTH):
                interrupted: set[str] = set()
                for left, right in itertools.pairwise(path):
                    interrupted |= influence[left][right]["interrupted_by"]
                found.append(
                    ConsequencePath(
                        nodes=tuple(path),
                        terminal_consequence=target,
                        interrupted_by=frozenset(interrupted),
                    )
                )

    found.sort(key=lambda p: (-int(p.terminal_consequence[1]), len(p.nodes), p.nodes))
    return found


@dataclass(frozen=True, slots=True)
class PathReduction:
    """Consequence-path reduction attributable to the engineering backstop."""

    minimum_class: str
    paths_before: int
    paths_after: int
    interrupted_paths: int

    @property
    def reduction_pct(self) -> float:
        """Percentage of high-consequence paths the control interrupts."""
        if self.paths_before == 0:
            return 0.0
        return 100.0 * self.interrupted_paths / self.paths_before

    def as_dict(self) -> dict[str, Any]:
        """Serialise for reporting."""
        return {
            "minimum_class": self.minimum_class,
            "reachable_paths_without_engineering_control": self.paths_before,
            "reachable_paths_with_engineering_control": self.paths_after,
            "interrupted_paths": self.interrupted_paths,
            "reduction_pct": round(self.reduction_pct, 2),
            "interpretation": (
                "Counts modelled dependency paths, not observed events. A path "
                "is a possibility in the architecture; whether it is exploitable "
                "is not established by this metric."
            ),
        }


def path_reduction(cgraph: ConsequenceGraph, *, minimum_class: str = "C4") -> PathReduction:
    """Measure how many high-consequence paths the engineering backstop interrupts."""
    paths = consequence_paths(cgraph, minimum_class=minimum_class)
    interrupted = sum(1 for path in paths if path.is_interrupted)
    return PathReduction(
        minimum_class=minimum_class,
        paths_before=len(paths),
        paths_after=len(paths) - interrupted,
        interrupted_paths=interrupted,
    )
