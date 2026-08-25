"""Architecture tests: the scenario safety boundary (ADR-006).

These are the tests that make BLACKSTART's safety claim structural rather than
aspirational. Widening the boundary requires deleting one of them, which is a
visible act in review rather than an accident.

The claim under test: **there is no code path from a scenario file to any system
outside the Python process.**
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from blackstart.scenario_engine.effects import EFFECT_REGISTRY

from tests.import_analysis import imported_modules, python_sources

pytestmark = pytest.mark.architecture

#: Packages that must remain free of any capability to act outside the process.
SEALED_PACKAGES = ("core", "scenario_engine")

#: Modules providing a way off the process. An import of any of these inside a
#: sealed package would breach the boundary.
FORBIDDEN_MODULES = frozenset(
    {
        "socket",
        "socketserver",
        "ssl",
        "subprocess",
        "multiprocessing",
        "asyncio",
        "http",
        "http.client",
        "urllib",
        "urllib.request",
        "ftplib",
        "smtplib",
        "telnetlib",
        "requests",
        "httpx",
        "aiohttp",
        "paramiko",
        "scapy",
        "pymodbus",
        "ctypes",
        "shutil",
    }
)

#: Callables that reach the operating system even without a forbidden import.
FORBIDDEN_CALLS = frozenset({"system", "popen", "execv", "execve", "spawnv", "fork"})

#: The complete effect vocabulary documented in ADR-006.
DOCUMENTED_EFFECTS = frozenset(
    {
        "demand.step",
        "demand.ramp",
        "source.depletion",
        "sensor.bias",
        "sensor.freeze",
        "supervisory.blackout",
        "setpoint.override",
    }
)


def sealed_sources(repo_root: Path) -> list[Path]:
    """Every source file in the sealed packages."""
    files: list[Path] = []
    for package in SEALED_PACKAGES:
        files.extend(python_sources(repo_root / "blackstart" / package))
    return files


class TestKernelPurity:
    def test_sealed_packages_import_nothing_that_leaves_the_process(self, repo_root: Path):
        """The structural basis of the whole safety boundary."""
        offences: list[str] = []
        for source in sealed_sources(repo_root):
            for module in imported_modules(source):
                root = module.split(".")[0]
                if module in FORBIDDEN_MODULES or root in FORBIDDEN_MODULES:
                    offences.append(f"{source.relative_to(repo_root)} imports {module}")
        assert not offences, "scenario safety boundary breached:\n" + "\n".join(offences)

    def test_sealed_packages_make_no_os_level_calls(self, repo_root: Path):
        """Catches `os.system` and friends, which need no forbidden import."""
        offences: list[str] = []
        for source in sealed_sources(repo_root):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in FORBIDDEN_CALLS
                ):
                    offences.append(
                        f"{source.relative_to(repo_root)}:{node.lineno} calls .{node.func.attr}()"
                    )
        assert not offences, "\n".join(offences)

    def test_the_physics_core_performs_no_file_io(self, repo_root: Path):
        """Evidence writing belongs to the evidence layer, not the kernel.

        Configuration loading is the one permitted read, and it lives in
        config.py at the boundary.
        """
        offences: list[str] = []
        for source in python_sources(repo_root / "blackstart" / "core"):
            if source.name in {"config.py", "build.py"}:
                continue  # configuration and asset-model loaders
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "open"
                ):
                    offences.append(f"{source.relative_to(repo_root)}:{node.lineno} calls open()")
        assert not offences, "\n".join(offences)

    def test_the_kernel_never_reads_the_wall_clock(self, repo_root: Path):
        """A wall-clock read in the scan loop would destroy reproducibility."""
        offences: list[str] = []
        for source in sealed_sources(repo_root):
            for module in imported_modules(source):
                if module.split(".")[0] in {"time", "datetime"}:
                    offences.append(f"{source.relative_to(repo_root)} imports {module}")
        assert not offences, (
            "simulation time is the only time axis in the kernel (ADR-005):\n" + "\n".join(offences)
        )


class TestEffectVocabulary:
    def test_registry_matches_the_documented_vocabulary_exactly(self):
        """The registry is closed. Adding an effect must be a deliberate act."""
        assert frozenset(EFFECT_REGISTRY) == DOCUMENTED_EFFECTS

    def test_the_adr_documents_every_registered_effect(self, repo_root: Path):
        adr = (repo_root / "docs" / "adr" / "ADR-006-scenario-safety-boundary.md").read_text(
            encoding="utf-8"
        )
        for name in EFFECT_REGISTRY:
            assert name in adr, f"effect '{name}' is not documented in ADR-006"

    def test_effects_receive_only_the_narrow_context(self, repo_root: Path):
        """An effect must not be handed a runner, a config writer, or a path."""
        source = (repo_root / "blackstart" / "scenario_engine" / "effects.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        context_fields: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EffectContext":
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        context_fields.add(stmt.target.id)
        assert context_fields == {"demand", "sensors", "truth", "setpoint"}


class TestNoOffensiveTooling:
    def test_no_protocol_or_exploitation_dependency_is_declared(self, repo_root: Path):
        """BLACKSTART studies effects and defences, not intrusion mechanisms."""
        pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8").lower()
        for package in ("scapy", "pymodbus", "impacket", "pwntools", "paramiko"):
            assert package not in pyproject, f"{package} must not be a dependency"

    def test_no_scanning_or_target_discovery_in_the_repository(self, repo_root: Path):
        """No code should be capable of reaching an address it was not given."""
        offences: list[str] = []
        for package in ("blackstart", "services"):
            for source in python_sources(repo_root / package):
                for module in imported_modules(source):
                    if module.split(".")[0] in {"nmap", "scapy", "masscan", "shodan"}:
                        offences.append(f"{source.relative_to(repo_root)}: {module}")
        assert not offences, "\n".join(offences)
