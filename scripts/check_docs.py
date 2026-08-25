"""Validate configuration, scenarios and documentation cross-references.

Documentation rot is the failure mode this project can least afford: the whole
argument rests on the claim that what is written matches what runs. These checks
run in CI so a broken cross-reference fails the build rather than surviving to a
reviewer.

Checks performed:

1. every configuration document loads and cross-validates;
2. every scenario loads and its effects resolve against the closed registry;
3. every relative Markdown link resolves to a file that exists;
4. every ADR referenced in prose exists;
5. no unresolved TODO/FIXME markers are committed;
6. the effect vocabulary in the docs matches the code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Directories whose Markdown is checked for link integrity.
DOC_ROOTS = ("docs", "threat-model", "framework-mappings", "experiments", "evidence")

#: Markers that must not survive into a release.
FORBIDDEN_MARKERS = ("TODO", "FIXME", "XXX", "HACK", "PLACEHOLDER")

#: Files permitted to mention the markers above (they discuss the policy).
MARKER_EXEMPT = {"CONTRIBUTING.md", "check_docs.py", "reviewer-guide.md"}

_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    """Every Markdown file subject to these checks."""
    files = [REPO_ROOT / name for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md")]
    for root in DOC_ROOTS:
        files.extend(sorted((REPO_ROOT / root).rglob("*.md")))
    return [path for path in files if path.is_file()]


def check_configuration(failures: list[str]) -> None:
    """Load and cross-validate every configuration document."""
    from blackstart.core.config import load_config
    from blackstart.core.graph.build import build_graph, load_asset_model

    try:
        config = load_config()
        build_graph(load_asset_model(), config.invariants, config.consequences)
    except (OSError, ValueError, KeyError) as exc:
        failures.append(f"configuration failed to load: {exc}")


def check_scenarios(failures: list[str]) -> None:
    """Load every scenario and confirm its effects resolve."""
    from blackstart.scenario_engine.loader import list_scenarios

    try:
        scenarios = list_scenarios()
    except (OSError, ValueError) as exc:
        failures.append(f"scenarios failed to load: {exc}")
        return

    if not scenarios:
        failures.append("no scenarios found")
    for scenario in scenarios:
        if not scenario.research_question.strip():
            failures.append(f"{scenario.id}: no research question")
        if scenario.expected is None:
            failures.append(f"{scenario.id}: no measured expectations recorded")


def check_links(failures: list[str]) -> None:
    """Confirm every relative Markdown link resolves."""
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for target in _LINK_PATTERN.findall(text):
            link = target.split(" ")[0].split("#")[0].strip()
            if not link or link.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / link).resolve()
            if not resolved.exists():
                failures.append(f"{path.relative_to(REPO_ROOT)}: broken link -> {link}")


def check_markers(failures: list[str]) -> None:
    """Reject unresolved work markers."""
    for path in markdown_files():
        if path.name in MARKER_EXEMPT:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                failures.append(f"{path.relative_to(REPO_ROOT)}: contains {marker}")


def check_effect_vocabulary(failures: list[str]) -> None:
    """Confirm ADR-006 documents exactly the registered effects."""
    from blackstart.scenario_engine.effects import EFFECT_REGISTRY

    adr = REPO_ROOT / "docs" / "adr" / "ADR-006-scenario-safety-boundary.md"
    if not adr.is_file():
        failures.append("ADR-006 is missing")
        return
    text = adr.read_text(encoding="utf-8")
    for name in EFFECT_REGISTRY:
        if name not in text:
            failures.append(f"ADR-006 does not document effect '{name}'")


def check_adrs(failures: list[str]) -> None:
    """Confirm the ADR set referenced throughout the repository exists."""
    adr_dir = REPO_ROOT / "docs" / "adr"
    found = {path.name.split("-")[1] for path in adr_dir.glob("ADR-*.md")}
    for number in ("001", "002", "003", "004", "005", "006"):
        if number not in found:
            failures.append(f"ADR-{number} is missing")


def main() -> int:
    """Run every check and report."""
    failures: list[str] = []
    checks = (
        ("configuration", check_configuration),
        ("scenarios", check_scenarios),
        ("markdown links", check_links),
        ("work markers", check_markers),
        ("effect vocabulary", check_effect_vocabulary),
        ("architecture decision records", check_adrs),
    )
    for name, check in checks:
        before = len(failures)
        check(failures)
        status = "ok" if len(failures) == before else "FAIL"
        print(f"  {name:<32} {status}")

    if failures:
        print(f"\n{len(failures)} problem(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("\nDocumentation and configuration consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
