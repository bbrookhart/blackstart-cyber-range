"""Unit tests for the consequence dependency graph and its queries."""

from __future__ import annotations

import pytest
from blackstart.core.config import BlackstartConfig
from blackstart.core.graph.build import build_graph, load_asset_model
from blackstart.core.graph.queries import (
    components_influencing,
    consequence_paths,
    path_reduction,
    supporting_assets,
)

pytestmark = pytest.mark.unit


class TestConstruction:
    def test_builds_from_shipped_configuration(self, consequence_graph):
        assert consequence_graph.node_count > 0
        assert consequence_graph.edge_count > 0

    def test_invariants_and_consequences_are_nodes(self, consequence_graph):
        assert set(consequence_graph.nodes_of_class("SafetyInvariant")) == {
            "INV-001",
            "INV-002",
            "INV-003",
            "INV-004",
            "INV-005",
        }
        assert set(consequence_graph.nodes_of_class("Consequence")) == {f"C{n}" for n in range(6)}

    def test_invariant_consequence_edges_come_from_invariant_config(
        self, consequence_graph, config: BlackstartConfig
    ):
        """The graph must not be able to disagree with the running invariants."""
        graph = consequence_graph.graph
        for spec in config.invariants.invariants:
            targets = {
                target
                for _, target, data in graph.out_edges(spec.id, data=True)
                if data.get("relation") == "CAN_CAUSE"
            }
            assert spec.severity_on_violation in targets

    def test_rejects_a_contradictory_invariant_mapping(self, config: BlackstartConfig):
        model = load_asset_model()
        payload = model.model_dump(mode="python", by_alias=True)
        payload["invariant_consequences"]["INV-001"] = "C1"
        broken = type(model).model_validate(payload)
        with pytest.raises(ValueError, match="severity_on_violation"):
            build_graph(broken, config.invariants, config.consequences)

    def test_rejects_an_edge_to_an_unknown_node(self, config: BlackstartConfig):
        model = load_asset_model()
        payload = model.model_dump(mode="python", by_alias=True)
        payload["edges"].append({"from": "CF-001", "to": "GHOST-999", "relation": "DEPENDS_ON"})
        broken = type(model).model_validate(payload)
        with pytest.raises(ValueError, match="unknown node"):
            build_graph(broken, config.invariants, config.consequences)

    def test_rejects_an_unknown_node_class(self):
        model = load_asset_model()
        payload = model.model_dump(mode="python", by_alias=True)
        payload["nodes"][0]["node_class"] = "Wormhole"
        with pytest.raises(ValueError, match="unknown node_class"):
            type(model).model_validate(payload)

    def test_rejects_an_unknown_relation(self):
        model = load_asset_model()
        payload = model.model_dump(mode="python", by_alias=True)
        payload["edges"][0]["relation"] = "VIBES_WITH"
        with pytest.raises(ValueError, match="unknown relation"):
            type(model).model_validate(payload)

    def test_missing_asset_model_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="asset model not found"):
            load_asset_model(tmp_path)


class TestQueries:
    def test_critical_function_is_supported_by_the_control_chain(self, consequence_graph):
        supporting = supporting_assets(consequence_graph, "CF-001")
        for expected in ("PLC-001", "PMP-001", "LIT-001", "HMI-001", "CTRL-LEVEL"):
            assert expected in supporting

    def test_critical_function_is_not_its_own_dependency(self, consequence_graph):
        assert "CF-001" not in supporting_assets(consequence_graph, "CF-001")

    def test_unknown_critical_function_raises(self, consequence_graph):
        with pytest.raises(KeyError, match="CF-999"):
            supporting_assets(consequence_graph, "CF-999")

    def test_operator_transmitter_can_influence_the_level_invariant(self, consequence_graph):
        """The dependency that makes SCN-003 possible."""
        assert "LIT-001" in components_influencing(consequence_graph, "INV-001")

    def test_independent_element_does_not_influence_the_level_invariant_via_control(
        self, consequence_graph
    ):
        """The independent element feeds only the backstop, which protects rather
        than commands. It must not appear as a way to *drive* INV-001."""
        influencers = components_influencing(consequence_graph, "INV-001")
        assert "LIT-002" not in influencers

    def test_unknown_invariant_raises(self, consequence_graph):
        with pytest.raises(KeyError, match="INV-999"):
            components_influencing(consequence_graph, "INV-999")


class TestConsequencePaths:
    def test_high_consequence_paths_exist(self, consequence_graph):
        paths = consequence_paths(consequence_graph, minimum_class="C4")
        assert paths, "the model should contain reachable high-consequence paths"

    def test_all_paths_terminate_at_or_above_the_requested_class(self, consequence_graph):
        for path in consequence_paths(consequence_graph, minimum_class="C4"):
            assert int(path.terminal_consequence[1]) >= 4

    def test_paths_are_sorted_most_severe_first(self, consequence_graph):
        paths = consequence_paths(consequence_graph, minimum_class="C3")
        ranks = [int(p.terminal_consequence[1]) for p in paths]
        assert ranks == sorted(ranks, reverse=True)

    def test_the_pump_command_path_is_interrupted_by_the_backstop(self, consequence_graph):
        paths = consequence_paths(consequence_graph, minimum_class="C4")
        through_control = [p for p in paths if "CTRL-LEVEL" in p.nodes and "PMP-001" in p.nodes]
        assert through_control
        for path in through_control:
            assert path.is_interrupted
            assert "BS-03" in path.interrupted_by

    def test_render_produces_an_arrow_chain(self, consequence_graph):
        path = consequence_paths(consequence_graph, minimum_class="C4")[0]
        assert " -> " in path.render()
        assert path.origin == path.nodes[0]


class TestPathReduction:
    def test_backstop_interrupts_some_high_consequence_paths(self, consequence_graph):
        reduction = path_reduction(consequence_graph, minimum_class="C4")
        assert reduction.paths_before > 0
        assert reduction.interrupted_paths > 0
        assert reduction.paths_after == reduction.paths_before - reduction.interrupted_paths

    def test_reduction_percentage_is_consistent(self, consequence_graph):
        reduction = path_reduction(consequence_graph, minimum_class="C4")
        expected = 100.0 * reduction.interrupted_paths / reduction.paths_before
        assert reduction.reduction_pct == pytest.approx(expected)

    def test_report_states_that_paths_are_not_events(self, consequence_graph):
        """The metric must not be readable as an empirical claim."""
        payload = path_reduction(consequence_graph).as_dict()
        assert "not observed events" in payload["interpretation"]

    def test_backstop_does_not_interrupt_every_path(self, consequence_graph):
        """An engineering control that removed all risk would be a modelling
        error, not a result."""
        reduction = path_reduction(consequence_graph, minimum_class="C4")
        assert reduction.paths_after > 0
