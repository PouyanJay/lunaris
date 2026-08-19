"""Reading imports out of Python source, for the repo-level structural guards.

Two guards sweep the tree and ask what each file imports: ``test_product_boundary.py`` (no Studio
module may name Lunaris Live) and ``test_dependency_closure.py`` (no app may import a workspace
package it does not declare). They had a copy of this walk each, which is the wrong shape for a
subtlety — the ``node.level`` handling below is not obvious, and a fix applied to one copy would
silently leave the other guard weaker than it looks.

Not a test module: the leading underscore keeps pytest from collecting it.
"""

from __future__ import annotations

import ast
from pathlib import Path


def imported_module_names(source: Path) -> set[str]:
    """The module names a file imports, from both ``import x`` and ``from x import y``.

    Returns names as written (``lunaris_live.graph``, not ``lunaris_live``) so a caller matching on
    a prefix and a caller wanting the top-level package can each get what they need from one walk.

    Relative imports (``node.level > 0``) are skipped: they name a package's own submodules, so
    counting them would attribute a package to itself. A file that will not parse returns nothing —
    a syntax error is a different guard's failure, and raising here would report it as this one's.
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a syntax error is another test's problem
        return set()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def imported_top_level_packages(source: Path) -> set[str]:
    """The distinct top-level packages a file imports — ``lunaris_live.graph`` counts as
    ``lunaris_live``.

    What a dependency question needs: a manifest declares a distribution, and a distribution ships a
    top-level package, so the dotted tail is noise once you are asking "is this declared?".
    """
    return {name.split(".")[0] for name in imported_module_names(source)}
