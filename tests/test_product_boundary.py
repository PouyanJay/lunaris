"""The one-way product boundary, Python side.

Lunaris Live may build on Studio's shared foundations; Studio must never depend on Live. That
direction is the whole basis for keeping both products in one repo — Live can be flagged off,
broken, or later lifted into its own repo without Studio noticing.

The web half is an ESLint rule (``apps/web/eslint.config.js``). This is the Python half. It was
written in Phase 0, before any Live package existed, so that the boundary would be enforced from
Live's first commit rather than retrofitted after something had already crossed it — and in Phase 1
it did exactly that, catching Live's compile plane being wired into Studio's shared composition
root on the day the package landed.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Import prefixes owned by Lunaris Live. Nothing outside Live may name these.
LIVE_PACKAGE_PREFIXES = ("lunaris_live",)

#: Where Live's own source lives — allowed to import itself.
#:
#: ``apps/api/.../live`` is Live's **region inside the shared API host** — the Python mirror of
#: the web's ``components/live/**`` exemption in ``apps/web/eslint.config.js``. One FastAPI app
#: serves both products, so somewhere has to name ``lunaris_live`` in order to mount Live's routes;
#: confining that to one directory is what keeps the boundary real. ``apps/api/tests/live`` is the
#: same region's tests — they exercise Live's endpoints and so must name Live, and putting them
#: anywhere else would mean either weakening this rule or testing Live's API through a keyhole.
#: Studio's own modules — including the shared composition root in ``dependencies.py`` — stay swept,
#: so Live cannot leak back into them. Keep this list short: every entry is a place the boundary
#: stops applying.
LIVE_SOURCE_DIRS = (
    "packages/live",
    "apps/api/src/lunaris_api/live",
    "apps/api/tests/live",
)


def _is_live_source(relative: str) -> bool:
    """Whether a repo-relative path lies inside one of Live's own directories.

    Matches on a directory *boundary*, not a string prefix: a bare ``startswith`` would also exempt
    a Studio module that merely begins with the same characters (``.../live_graph_service.py``
    beside ``.../live/``), silently widening the exemption to files nobody meant to exempt.
    """
    return any(
        relative == live_dir or relative.startswith(f"{live_dir}/") for live_dir in LIVE_SOURCE_DIRS
    )


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
            if _is_live_source(relative):
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

    Live's own directories are exempt (``LIVE_SOURCE_DIRS``) — including its region inside the
    shared API host, which is the one place allowed to mount Live's routes.
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

    # Studio's shared composition root must stay swept — it is the single most likely place for a
    # Live dependency to be wired in "just for now", and it sits right beside Live's own region.
    composition_root = REPO_ROOT / "apps/api/src/lunaris_api/dependencies.py"
    assert composition_root in sources, "Studio's composition root must remain inside the sweep"


def test_the_live_exemption_stops_at_a_directory_boundary() -> None:
    """The exemption must cover Live's directory and nothing that merely looks like it.

    ``apps/api/src/lunaris_api/live/`` is exempt; a Studio module named ``live_*.py`` in the same
    package is not. Written as its own test because the difference is one character in the matcher
    and the failure mode — a Studio file quietly stopping being checked — is invisible otherwise.
    """
    assert _is_live_source("apps/api/src/lunaris_api/live/router.py")
    assert _is_live_source("apps/api/tests/live/test_live_graphs_api.py")
    assert _is_live_source("packages/live/src/lunaris_live/graph/assembly.py")

    assert not _is_live_source("apps/api/src/lunaris_api/live_graph_service.py")
    assert not _is_live_source("apps/api/tests/live_helpers.py")
    assert not _is_live_source("packages/live_experiment/src/thing.py")
