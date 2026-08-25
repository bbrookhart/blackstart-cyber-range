"""Static import analysis helpers shared by the unit and architecture suites.

These walk the AST rather than grepping source text. Text matching produces false
positives on prose -- a docstring that *describes* a boundary would be read as
crossing it -- which would make the guarantee untestable in exactly the modules
that document it most carefully.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__ = ["imported_modules", "python_sources"]


def python_sources(package_dir: Path) -> list[Path]:
    """Every Python source file under a package directory."""
    return sorted(package_dir.rglob("*.py"))


def imported_modules(source_path: Path) -> set[str]:
    """Return every module name imported by a source file.

    Both ``import x.y`` and ``from x.y import z`` forms are resolved to the
    dotted module path. Relative imports are returned with their leading dots
    stripped, which is sufficient for the prefix checks these tests perform.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules
