"""BLACKSTART command-line interface.

The design goal is that a reviewer can reproduce the flagship result without
reading any source. Commands are nouns and verbs, every command prints where its
output went, and nothing writes outside the evidence root.

``argparse`` is used deliberately: the CLI is a thin research harness, and a
zero-dependency implementation keeps the dependency-audit surface honest.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from blackstart import __version__
from blackstart.analysis.compare import VariantRun, compare_variants
from blackstart.analysis.metrics import compute_metrics
from blackstart.core.config import BlackstartConfig, load_config
from blackstart.core.graph.build import build_graph, load_asset_model
from blackstart.core.graph.queries import (
    components_influencing,
    consequence_paths,
    path_reduction,
    supporting_assets,
)
from blackstart.evidence.package import write_evidence
from blackstart.evidence.verify import reproduce_experiment, verify_evidence
from blackstart.scenario_engine.loader import list_scenarios, load_scenario
from blackstart.scenario_engine.orchestration import (
    ExperimentResult,
    ExperimentRunner,
    resolve_variant,
)

__all__ = ["build_parser", "main"]

DEFAULT_EVIDENCE_ROOT = Path("evidence")

_EXIT_OK = 0
_EXIT_FAILURE = 1
_EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="blackstart",
        description=(
            "BLACKSTART — a consequence-driven cyber-physical resilience range. "
            "Assume compromise. Preserve the mission."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Reviewer path:\n"
            "  blackstart scenario list\n"
            "  blackstart experiment run SCN-001\n"
            "  blackstart experiment compare SCN-004\n"
            "  blackstart evidence verify --all\n"
            "  blackstart graph paths --min-class C4\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"blackstart {__version__}")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory holding process/invariants/consequences/architecture YAML.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    # --- scenario ----------------------------------------------------------
    scenario = subcommands.add_parser("scenario", help="Inspect the scenario catalogue.")
    scenario_sub = scenario.add_subparsers(dest="scenario_command", required=True)
    scenario_sub.add_parser("list", help="List available scenarios.")
    show = scenario_sub.add_parser("show", help="Show one scenario in full.")
    show.add_argument("scenario_id", help="Scenario identifier, e.g. SCN-004.")

    # --- experiment --------------------------------------------------------
    experiment = subcommands.add_parser("experiment", help="Run and compare experiments.")
    experiment_sub = experiment.add_subparsers(dest="experiment_command", required=True)

    run = experiment_sub.add_parser("run", help="Run one scenario under one variant.")
    run.add_argument("scenario_id", help="Scenario identifier, e.g. SCN-001.")
    run.add_argument(
        "--variant",
        default="backstop-enabled",
        help="Experiment variant (default: backstop-enabled).",
    )
    run.add_argument("--seed", type=int, default=None, help="Override the scenario seed.")
    run.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help="Directory to write the evidence package into.",
    )

    compare = experiment_sub.add_parser(
        "compare", help="Run one scenario under two variants and compare the outcomes."
    )
    compare.add_argument("scenario_id", help="Scenario identifier, e.g. SCN-004.")
    compare.add_argument(
        "--variant",
        action="append",
        dest="variants",
        default=None,
        help=(
            "Variant to include; repeat for each. Default: backstop-disabled and backstop-enabled."
        ),
    )
    compare.add_argument("--seed", type=int, default=None, help="Override the scenario seed.")
    compare.add_argument(
        "--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT, help="Evidence output root."
    )
    compare.add_argument("--json", action="store_true", help="Emit the comparison as JSON.")

    # --- evidence ----------------------------------------------------------
    evidence = subcommands.add_parser("evidence", help="Verify evidence packages.")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    verify = evidence_sub.add_parser(
        "verify", help="Check evidence integrity, and optionally reproduce the experiment."
    )
    verify.add_argument(
        "experiment_id", nargs="?", default=None, help="Experiment identifier, or omit with --all."
    )
    verify.add_argument("--all", action="store_true", help="Verify every package under the root.")
    verify.add_argument(
        "--reproduce",
        action="store_true",
        help="Re-execute the experiment and compare artefacts byte-for-byte.",
    )
    verify.add_argument(
        "--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT, help="Evidence root."
    )
    verify.add_argument("--json", action="store_true", help="Emit the report as JSON.")

    # --- graph -------------------------------------------------------------
    graph = subcommands.add_parser("graph", help="Query the consequence dependency graph.")
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)

    supports = graph_sub.add_parser("supports", help="What supports a critical function?")
    supports.add_argument("--critical-function", default="CF-001")

    influences = graph_sub.add_parser(
        "influences", help="Which components can influence a safety invariant?"
    )
    influences.add_argument("invariant_id", help="Invariant identifier, e.g. INV-001.")

    paths = graph_sub.add_parser(
        "paths", help="Enumerate dependency paths terminating in a high consequence."
    )
    paths.add_argument("--min-class", default="C4", help="Lowest consequence class (default C4).")
    paths.add_argument("--json", action="store_true", help="Emit as JSON.")

    reduction = graph_sub.add_parser(
        "reduction", help="Consequence-path reduction from the engineering backstop."
    )
    reduction.add_argument("--min-class", default="C4")

    # --- config ------------------------------------------------------------
    config_cmd = subcommands.add_parser("config", help="Validate configuration.")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("validate", help="Load and cross-validate every configuration file.")

    return parser


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _run_one(
    config: BlackstartConfig,
    scenario_id: str,
    variant_name: str,
    seed: int | None,
    evidence_root: Path,
) -> tuple[ExperimentResult, dict[str, Any], Path]:
    """Execute one experiment and write its evidence package."""
    scenario = load_scenario(scenario_id)
    variant = resolve_variant(variant_name)
    runner = ExperimentRunner(config, scenario, variant, seed_override=seed)
    result = runner.run()
    metrics = compute_metrics(result, config)
    result.metrics = metrics
    directory = write_evidence(result, config, metrics, evidence_root)
    return result, metrics, directory


def _cmd_scenario_list(_: argparse.Namespace) -> int:
    """List the scenario catalogue."""
    scenarios = list_scenarios()
    if not scenarios:
        print("No scenarios found.")
        return _EXIT_OK
    print(f"{'ID':<9} {'CATEGORY':<21} {'SEED':>5} {'DURATION':>9}  NAME")
    for scenario in scenarios:
        print(
            f"{scenario.id:<9} {scenario.category:<21} {scenario.seed:>5} "
            f"{scenario.duration_s:>8.0f}s  {scenario.name}"
        )
    return _EXIT_OK


def _cmd_scenario_show(args: argparse.Namespace) -> int:
    """Print one scenario in full."""
    scenario = load_scenario(args.scenario_id)
    print(f"{scenario.id} — {scenario.name}")
    print(f"Category   {scenario.category}")
    print(f"Seed       {scenario.seed}")
    print(f"Duration   {scenario.duration_s:.0f} s")
    print(f"\nResearch question\n  {scenario.research_question}")
    print(f"\nDescription\n  {scenario.description.strip()}")
    if scenario.events:
        print("\nEvents")
        for event in scenario.events:
            window = (
                f"t={event.t_s:.0f}s"
                if event.duration_s is None
                else f"t={event.t_s:.0f}s for {event.duration_s:.0f}s"
            )
            attack = f"  [ATT&CK ICS: {', '.join(event.attack_ics)}]" if event.attack_ics else ""
            print(f"  {window:<22} {event.effect:<22} {event.description}{attack}")
    else:
        print("\nEvents\n  (none — nominal operation)")
    if scenario.notes:
        print(f"\nNotes\n  {scenario.notes.strip()}")
    return _EXIT_OK


def _cmd_experiment_run(args: argparse.Namespace, config: BlackstartConfig) -> int:
    """Run one experiment and report its headline metrics."""
    result, metrics, directory = _run_one(
        config, args.scenario_id, args.variant, args.seed, args.evidence_root
    )
    print(f"Experiment  {result.experiment_id}")
    print(f"Scenario    {result.scenario.id} — {result.scenario.name}")
    print(f"Variant     {result.variant.name}")
    print(f"Seed        {result.seed}   Config hash {result.configuration_hash[:16]}")
    print("")
    print(f"Maximum consequence      {metrics['maximum_consequence']}")
    print(f"Invariant violations     {metrics['invariant_violations_total']}")
    violated = ", ".join(metrics["violated_invariants"]) or "none"
    print(f"Violated invariants      {violated}")
    print(f"Service availability     {metrics['service_availability_pct']:.2f}%")
    print(f"Unsafe-state duration    {metrics['unsafe_state_duration_s']:.1f} s")
    print(f"Maximum tank level       {metrics['max_tank_level_m']:.3f} m")
    print(f"Spill volume             {metrics['spill_volume_m3']:.3f} m3")
    print("")
    print(f"Evidence    {directory}")
    return _EXIT_OK


def _cmd_experiment_compare(args: argparse.Namespace, config: BlackstartConfig) -> int:
    """Run several variants of one scenario and compare them."""
    variant_names = args.variants or ["backstop-disabled", "backstop-enabled"]
    runs = []
    for name in variant_names:
        result, metrics, directory = _run_one(
            config, args.scenario_id, name, args.seed, args.evidence_root
        )
        runs.append(VariantRun(result=result, metrics=metrics))
        print(f"[{name}] {result.experiment_id} -> {directory}", file=sys.stderr)

    asset_model = load_asset_model(args.config_dir)
    cgraph = build_graph(asset_model, config.invariants, config.consequences)
    reduction = path_reduction(cgraph, minimum_class="C4").as_dict()

    report = compare_variants(runs, path_reduction=reduction)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print("")
        print(report.render())
        print("")
        print(
            f"Architectural consequence-path reduction (C4+): "
            f"{reduction['reachable_paths_without_engineering_control']} -> "
            f"{reduction['reachable_paths_with_engineering_control']} paths "
            f"({reduction['reduction_pct']:.0f}% interrupted)"
        )
        print(f"  {reduction['interpretation']}")
    return _EXIT_OK


def _cmd_evidence_verify(args: argparse.Namespace) -> int:
    """Verify one or all evidence packages."""
    root: Path = args.evidence_root
    if args.all or args.experiment_id is None:
        directories = sorted(p for p in root.glob("**/EXP-*") if p.is_dir())
        if not directories:
            print(f"No evidence packages found under {root}", file=sys.stderr)
            return _EXIT_FAILURE
    else:
        candidates = sorted(root.glob(f"**/{args.experiment_id}"))
        if not candidates:
            print(f"No evidence package '{args.experiment_id}' under {root}", file=sys.stderr)
            return _EXIT_FAILURE
        directories = candidates

    reports = []
    overall_ok = True
    for directory in directories:
        report = verify_evidence(directory)
        if report.passed and args.reproduce:
            reproduction = reproduce_experiment(directory)
            report.checks.extend(reproduction.checks)
            report.errors.extend(reproduction.errors)
            report.passed = report.passed and reproduction.passed
        reports.append(report)
        overall_ok = overall_ok and report.passed

        if not args.json:
            status = "PASS" if report.passed else "FAIL"
            checks = len(report.checks)
            print(f"[{status}] {report.experiment_id}  ({checks} checks)")
            for error in report.errors:
                print(f"         {error}")

    if args.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2, sort_keys=True))
    elif overall_ok:
        note = " and reproduced" if args.reproduce else ""
        print(f"\n{len(reports)} evidence package(s) verified{note}.")

    return _EXIT_OK if overall_ok else _EXIT_FAILURE


def _cmd_graph(args: argparse.Namespace, config: BlackstartConfig) -> int:
    """Answer a dependency-graph query."""
    asset_model = load_asset_model(args.config_dir)
    cgraph = build_graph(asset_model, config.invariants, config.consequences)

    match args.graph_command:
        case "supports":
            assets = supporting_assets(cgraph, args.critical_function)
            print(f"{len(assets)} components support {args.critical_function}:")
            for node in assets:
                print(f"  {node:<14} {cgraph.label(node)}")
        case "influences":
            components = components_influencing(cgraph, args.invariant_id)
            print(f"{len(components)} components can influence {args.invariant_id}:")
            for node in components:
                print(f"  {node:<14} {cgraph.label(node)}")
        case "paths":
            paths = consequence_paths(cgraph, minimum_class=args.min_class)
            if args.json:
                print(json.dumps([p.as_dict() for p in paths], indent=2))
            else:
                print(f"{len(paths)} dependency path(s) terminating at {args.min_class} or above:")
                for path in paths:
                    marker = (
                        f"  [interrupted by {', '.join(sorted(path.interrupted_by))}]"
                        if path.is_interrupted
                        else "  [NOT INTERRUPTED]"
                    )
                    print(f"  {path.render()}{marker}")
        case "reduction":
            reduction = path_reduction(cgraph, minimum_class=args.min_class).as_dict()
            print(json.dumps(reduction, indent=2))
    return _EXIT_OK


def _cmd_config_validate(config: BlackstartConfig, config_dir: Path | None) -> int:
    """Report that all configuration loaded and cross-validated."""
    asset_model = load_asset_model(config_dir)
    cgraph = build_graph(asset_model, config.invariants, config.consequences)
    scenarios = list_scenarios()
    print("Configuration valid.")
    print(
        f"  process           {config.process.process_id} "
        f"(dt={config.process.simulation.timestep_s}s, "
        f"tau={config.process.dominant_time_constant_s:.0f}s)"
    )
    print(f"  invariants        {len(config.invariants.invariants)}")
    print(f"  consequences      {len(config.consequences.consequences)} classes")
    print(f"  zones             {len(config.architecture.zones)}")
    print(f"  services          {len(config.architecture.services)}")
    print(f"  conduits          {len(config.architecture.conduits)}")
    print(f"  backstop rules    {len(config.architecture.backstop.rules)}")
    print(f"  graph             {cgraph.node_count} nodes, {cgraph.edge_count} edges")
    print(f"  scenarios         {len(scenarios)}")
    return _EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        Process exit status: 0 success, 1 a check failed, 2 a usage or
        configuration error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "scenario":
            if args.scenario_command == "list":
                return _cmd_scenario_list(args)
            return _cmd_scenario_show(args)

        if args.command == "evidence":
            return _cmd_evidence_verify(args)

        config = load_config(args.config_dir)

        if args.command == "experiment":
            if args.experiment_command == "run":
                return _cmd_experiment_run(args, config)
            return _cmd_experiment_compare(args, config)

        if args.command == "graph":
            return _cmd_graph(args, config)

        if args.command == "config":
            return _cmd_config_validate(config, args.config_dir)

    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    # argparse.error() is NoReturn: it prints usage and exits.
    parser.error(f"unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
