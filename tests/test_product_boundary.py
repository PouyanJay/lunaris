"""The one-way product boundary, Python side.

Lunaris Live may build on Studio's shared foundations; Studio must never depend on Live. That
direction is the whole basis for keeping both products in one repo — Live can be flagged off,
broken, or later lifted into its own repo without Studio noticing.

The web half is an ESLint rule (``apps/web/eslint.config.js``). This is the Python half. It is
deliberately written before ``packages/live_*`` exists: today it passes vacuously, and the moment
Phase 1 adds the first Live package it starts enforcing without anyone having to remember to add it.
The alternative — adding the rule alongside the code it constrains — is exactly how a boundary gets
crossed once "just for now" and then stays crossed.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Import prefixes owned by Lunaris Live. Nothing outside Live may name these.
LIVE_PACKAGE_PREFIXES = ("lunaris_live",)

#: Where Live's own source lives — allowed to import itself.
LIVE_SOURCE_DIRS = ("packages/live",)


def _studio_python_sources() -> list[Path]:
    """Every Python source file that belongs to Studio rather than Live."""
    roots = [REPO_ROOT / "packages", REPO_ROOT / "apps"]
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if "__pycache__" in relative or "/.venv/" in relative:
                continue
            if any(relative.startswith(live_dir) for live_dir in LIVE_SOURCE_DIRS):
                continue
            files.append(path)
    return files


def _imported_modules(source: Path) -> set[str]:
    """The top-level module names a file imports, from both `import x` and `from x import y`."""
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


def test_studio_never_imports_live() -> None:
    """No Studio module may import a Lunaris Live package.

    Passes vacuously until Phase 1 creates the first ``packages/live_*``; it exists so that the
    boundary is enforced from that package's first commit rather than retrofitted after something
    has already crossed it.
    """
    offenders: list[str] = []
    for source in _studio_python_sources():
        for module in _imported_modules(source):
            if module.startswith(LIVE_PACKAGE_PREFIXES):
                relative = source.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{relative} imports {module}")

    assert not offenders, (
        "Studio must not import Lunaris Live — Live depends on Studio's foundations, never the "
        "reverse:\n  " + "\n  ".join(sorted(offenders))
    )


def test_boundary_check_actually_inspects_studio_sources() -> None:
    """Guard the guard.

    ``test_studio_never_imports_live`` passes trivially while Live does not exist, so it would also
    pass if the file discovery silently broke and found nothing. This pins that the sweep really is
    reading Studio's source, and really does parse imports out of it.
    """
    sources = _studio_python_sources()
    assert len(sources) > 100, f"expected to sweep Studio's Python sources, found {len(sources)}"

    agent_package = REPO_ROOT / "packages/agent/src/lunaris_agent/harness/agent.py"
    assert agent_package in sources, "the sweep should cover the agent harness"
    assert _imported_modules(agent_package), "the import extractor returned nothing for a real file"
