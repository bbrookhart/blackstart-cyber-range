"""Regenerate ``threat-model/consequence-paths.yaml`` from the dependency graph.

The enumerated consequence paths are a *derived* artefact. Hand-authoring them
would guarantee they eventually describe a model that no longer exists, which is
the failure mode this whole repository is arranged to avoid.

Usage::

    uv run python scripts/generate_consequence_paths.py > threat-model/consequence-paths.yaml

``tests/unit/test_consequence_paths_doc.py`` asserts the committed file still
matches the graph.
"""

from __future__ import annotations

import sys

from blackstart.core.config import load_config
from blackstart.core.graph.build import build_graph, load_asset_model
from blackstart.core.graph.queries import consequence_paths, path_reduction

MINIMUM_CLASS = "C4"

_HEADER = """# BLACKSTART — enumerated high-consequence dependency paths
#
# GENERATED from the dependency graph in configs/assets.yaml. Do not hand-edit:
# regenerate with
#
#     uv run python scripts/generate_consequence_paths.py > threat-model/consequence-paths.yaml
#
# tests/unit/test_consequence_paths_doc.py asserts that every path listed here
# still exists in the graph and that the counts match, so this file cannot drift
# away from the model it describes.
#
# WHAT A PATH IS: a route by which a change in one modelled component can
# influence a physical outcome severe enough to be classified C4 or above. It is
# a MODELLED POSSIBILITY, not an observed event and not a demonstrated attack.
# Whether any path is exploitable against a real system is not established here.
#
# `interrupted_by` names the engineering-backstop rules that break the path."""


def main() -> int:
    """Emit the generated YAML document on standard output."""
    config = load_config()
    graph = build_graph(load_asset_model(), config.invariants, config.consequences)
    paths = consequence_paths(graph, minimum_class=MINIMUM_CLASS)
    reduction = path_reduction(graph, minimum_class=MINIMUM_CLASS)

    out = sys.stdout
    out.write(_HEADER + "\n\n")
    out.write("schema_version: 1\n")
    out.write(f'minimum_class: "{reduction.minimum_class}"\n')
    out.write("summary:\n")
    out.write(f"  total_paths: {reduction.paths_before}\n")
    out.write(f"  interrupted_by_engineering_control: {reduction.interrupted_paths}\n")
    out.write(f"  remaining_uninterrupted: {reduction.paths_after}\n")
    out.write(f"  reduction_pct: {reduction.reduction_pct:.1f}\n\n")
    out.write("paths:\n")

    for index, path in enumerate(paths, start=1):
        rules = ", ".join(f'"{rule}"' for rule in sorted(path.interrupted_by))
        nodes = ", ".join(f'"{node}"' for node in path.nodes)
        out.write(f'  - id: "CP-{index:03d}"\n')
        out.write(f'    terminal_consequence: "{path.terminal_consequence}"\n')
        out.write(f'    origin: "{path.origin}"\n')
        out.write(f"    path: [{nodes}]\n")
        out.write(f"    interrupted_by: [{rules}]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
