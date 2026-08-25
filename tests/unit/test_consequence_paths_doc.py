"""The committed consequence-path analysis must match the live graph.

``threat-model/consequence-paths.yaml`` is a derived artefact. A hand-edited or
stale copy would describe a model that no longer exists, which is exactly the
documentation rot this repository is arranged to prevent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from blackstart.core.graph.queries import consequence_paths, path_reduction

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def document(request: pytest.FixtureRequest) -> dict[str, Any]:
    root = Path(request.config.rootpath)
    path = root / "threat-model" / "consequence-paths.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class TestConsequencePathDocument:
    def test_summary_counts_match_the_graph(self, document, consequence_graph):
        reduction = path_reduction(consequence_graph, minimum_class=document["minimum_class"])
        summary = document["summary"]
        assert summary["total_paths"] == reduction.paths_before
        assert summary["interrupted_by_engineering_control"] == reduction.interrupted_paths
        assert summary["remaining_uninterrupted"] == reduction.paths_after

    def test_every_documented_path_exists_in_the_graph(self, document, consequence_graph):
        live = {
            tuple(path.nodes): path
            for path in consequence_paths(
                consequence_graph, minimum_class=document["minimum_class"]
            )
        }
        for entry in document["paths"]:
            nodes = tuple(entry["path"])
            assert nodes in live, f"{entry['id']} no longer exists in the graph"

    def test_documented_interruptions_match_the_graph(self, document, consequence_graph):
        live = {
            tuple(path.nodes): path
            for path in consequence_paths(
                consequence_graph, minimum_class=document["minimum_class"]
            )
        }
        for entry in document["paths"]:
            path = live[tuple(entry["path"])]
            assert sorted(entry["interrupted_by"]) == sorted(path.interrupted_by), (
                f"{entry['id']}: documented mitigation differs from the model"
            )

    def test_no_path_is_documented_that_the_graph_does_not_produce(
        self, document, consequence_graph
    ):
        live_count = len(
            consequence_paths(consequence_graph, minimum_class=document["minimum_class"])
        )
        assert len(document["paths"]) == live_count

    def test_the_valve_command_path_is_recorded_as_uninterrupted(self, document):
        """A known, deliberate gap: the backstop constrains the pump command
        path and does nothing for the outlet valve. It must stay visible."""
        valve_paths = [
            entry
            for entry in document["paths"]
            if "VLV-001" in entry["path"] and "CTRL-RESERVE" in entry["path"]
        ]
        assert valve_paths, "expected valve command paths in the model"
        for entry in valve_paths:
            assert entry["interrupted_by"] == []
