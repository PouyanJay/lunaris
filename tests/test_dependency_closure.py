"""Every workspace package a member imports must be one that member declares.

A ``pyproject.toml`` is not documentation — it is the exact set of packages that gets installed into
the container image. ``uv sync --package lunaris-api`` resolves the *declared* closure and nothing
else, so a module that is importable in the dev venv (where the whole workspace is installed) can be
missing from the image built from the same source.

That failure is invisible locally and total in production: the import is at module scope, so the
process dies at startup rather than degrading. It is also invisible to a normal test run, because
pytest runs against the full workspace venv where every package is present.

This is not hypothetical, twice over. ``apps/api`` imported ``lunaris_live`` from Phase 1
(2026-08-09) without declaring it, and every ``CD (dev)`` run failed from that commit onward —
caught only by ``Dockerfile.cover``'s build-time import assertion, and only after the code had
merged twice. Widening this sweep from the apps to every workspace member then found a second,
older instance: ``lunaris-agent`` importing ``lunaris_grounding`` undeclared, masked because
``apps/api`` happened to declare both.

**What this does not catch.** Only static ``import`` statements are visible to it, so a dynamic
``importlib.import_module("lunaris_live")`` would slip through (the sibling
``test_product_boundary.py`` shares that limit — neither guard can see a name assembled at runtime).
Conversely, an import used only under ``TYPE_CHECKING`` *is* flagged, because the AST walk does not
distinguish conditional branches. That asymmetry is deliberate: this check errs toward demanding a
declaration, which costs a manifest line, rather than toward missing one, which costs an outage.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from _source_scan import imported_top_level_packages

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _workspace_member_dirs() -> list[Path]:
    """Every uv workspace member directory, expanded from the root manifest's globs."""
    root = _load_toml(REPO_ROOT / "pyproject.toml")
    patterns = root["tool"]["uv"]["workspace"]["members"]
    members: list[Path] = []
    for pattern in patterns:
        members.extend(sorted(path for path in REPO_ROOT.glob(pattern) if path.is_dir()))
    return members


def _import_name_to_distribution() -> dict[str, str]:
    """Map each workspace package's *import* name to its *distribution* name.

    They differ by a hyphen/underscore convention (``lunaris-live`` ships ``lunaris_live``), and the
    manifest declares one while the source imports the other — which is precisely the gap a
    hand-maintained dependency list falls through. Read from each member's wheel-packages setting
    rather than guessed from the distribution name, so a package whose import name diverges is
    mapped correctly instead of silently skipped.
    """
    mapping: dict[str, str] = {}
    for member in _workspace_member_dirs():
        manifest = member / "pyproject.toml"
        if not manifest.is_file():
            continue
        data = _load_toml(manifest)
        distribution = data["project"]["name"]
        wheel_packages = (
            data.get("tool", {})
            .get("hatch", {})
            .get("build", {})
            .get("targets", {})
            .get("wheel", {})
        ).get("packages", [])
        for entry in wheel_packages:
            mapping[Path(entry).name] = distribution
    return mapping


def _checked_members() -> list[Path]:
    """The workspace members this check applies to: everything that ships a ``src/`` tree.

    Both the deployable apps and the libraries, deliberately — see
    ``test_the_sweep_covers_the_libraries_and_not_only_the_apps`` for why the breadth is pinned
    separately rather than left implicit in the loop below.
    """
    return [
        member
        for member in _workspace_member_dirs()
        if (member / "pyproject.toml").is_file() and (member / "src").is_dir()
    ]


def _shipped_sources(member_dir: Path, *, root: Path = REPO_ROOT) -> list[Path]:
    """The member's shipped Python sources — ``src/`` only.

    Tests are excluded deliberately: they run in the dev venv, never in a built wheel or image, so a
    test-only import is not a packaging defect and requiring it in the manifest would push test
    dependencies into production containers.
    """
    src = member_dir / "src"
    return [
        path
        for path in sorted(src.rglob("*.py"))
        if "__pycache__" not in path.relative_to(root).as_posix()
    ]


#: Everything that can follow a distribution name in a PEP 508 requirement: an extras bracket, any
#: comparison operator, an environment marker, or whitespace. Split once on the first of them and
#: what remains is the name — ``lunaris-video[render]>=1 ; python_version < "3.13"`` is a
#: declaration of ``lunaris-video``. Written as one pattern rather than a chain of ``str.split``
#: calls so its correctness is visible instead of needing to be traced through compound operators
#: like ``~=`` and ``!=``.
_REQUIREMENT_NAME_END = re.compile(r"[\[<>=!~;\s]")


def _declared_dependencies(member_dir: Path) -> set[str]:
    """The distribution names the member declares, across required and optional dependencies."""
    project = _load_toml(member_dir / "pyproject.toml")["project"]
    raw = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        raw.extend(extra)
    return {name for name in (_REQUIREMENT_NAME_END.split(r.strip(), 1)[0] for r in raw) if name}


def undeclared_workspace_imports(
    member_dir: Path, import_to_distribution: dict[str, str], *, root: Path = REPO_ROOT
) -> list[str]:
    """Workspace packages the member's shipped source imports without declaring, one line each.

    A function rather than an inlined loop so it can be aimed at a *synthetic* member whose defect
    is known — see ``test_the_checker_names_an_undeclared_import``. Without that, the only
    assertion available is "the real tree has no offenders", which passes just as happily when the
    detection is broken as when the manifests are right. Mutation testing found exactly that:
    neutering the offender collection left the suite green.
    """
    own_name = _load_toml(member_dir / "pyproject.toml")["project"]["name"]
    declared = _declared_dependencies(member_dir)

    offenders: list[str] = []
    for source in _shipped_sources(member_dir, root=root):
        for module in imported_top_level_packages(source):
            distribution = import_to_distribution.get(module)
            if distribution is None:
                continue  # third-party or stdlib — pip/uv resolves it, not this test
            if distribution == own_name:
                continue  # the member importing itself
            if distribution not in declared:
                relative = source.relative_to(root).as_posix()
                offenders.append(f"{relative} imports {module} ({distribution}), not declared")
    return sorted(set(offenders))


def test_every_workspace_package_a_member_imports_is_declared() -> None:
    """Every workspace member's manifest must cover the workspace packages its source imports.

    The failure this pins is a container that cannot start: ``uv sync --package <app>`` installs the
    declared closure, so an undeclared workspace import is a ``ModuleNotFoundError`` at the first
    line of ``uvicorn``.

    Libraries under ``packages/`` are swept too, not just the deployable apps. An app's closure can
    mask a library's broken manifest — ``lunaris-agent`` imported ``lunaris_grounding`` undeclared
    for a long time and nothing noticed, because ``apps/api`` happened to declare both, so the
    package a library needed was present by coincidence rather than by its own manifest being right.
    That coincidence lasts exactly until a second app consumes the library, or until the first app's
    dependency list is pruned.
    """
    import_to_distribution = _import_name_to_distribution()
    offenders = [
        offender
        for member in _checked_members()
        for offender in undeclared_workspace_imports(member, import_to_distribution)
    ]

    assert not offenders, (
        "These workspace packages are imported but not declared, so they will be ABSENT from the "
        "built wheel or container image:\n  "
        + "\n  ".join(offenders)
        + "\n\nAdd each to that member's [project.dependencies] and [tool.uv.sources], then "
        "re-lock."
    )


def test_the_sweep_covers_the_libraries_and_not_only_the_apps() -> None:
    """The *breadth* of the sweep is itself load-bearing, so it gets its own assertion.

    Mutation testing caught this: with every manifest correct, narrowing the sweep back to
    ``apps/api`` alone left the whole suite green, because a narrower sweep and a clean tree are
    indistinguishable when you only ever assert "no offenders found". The breadth is exactly what
    found ``lunaris-agent``'s undeclared ``lunaris_grounding``, so losing it silently would give
    back the ground this task gained.
    """
    swept = {member.relative_to(REPO_ROOT).as_posix() for member in _checked_members()}

    assert "apps/api" in swept, "the deployable app must be swept"
    assert "packages/agent" in swept, (
        "libraries must be swept too — packages/agent is the member whose broken manifest an app's "
        "closure was masking"
    )
    assert len([name for name in swept if name.startswith("packages/")]) >= 6, (
        f"expected the workspace's libraries to be swept, got {sorted(swept)}"
    )


def _write_synthetic_app(root: Path, *, declares: str, imports: str) -> Path:
    """An app on disk with one dependency declaration and one import, for aiming the checker at."""
    app_dir = root / "apps/synthetic"
    (app_dir / "src").mkdir(parents=True)
    (app_dir / "pyproject.toml").write_text(
        f'[project]\nname = "synthetic-app"\ndependencies = [{declares}]\n'
    )
    (app_dir / "src" / "thing.py").write_text(f"import {imports}\n")
    return app_dir


def test_the_checker_names_an_undeclared_import(tmp_path: Path) -> None:
    """Aimed at an app that HAS the defect, the checker must name it.

    This is the positive half, and it is the one that has teeth. Every other assertion here is of
    the form "nothing found", which a broken detector satisfies trivially — so without this test,
    deleting the detection logic outright leaves the suite green. It did, until this was written.
    """
    app_dir = _write_synthetic_app(tmp_path, declares='"fastapi>=0.115"', imports="lunaris_live")

    offenders = undeclared_workspace_imports(
        app_dir, {"lunaris_live": "lunaris-live"}, root=tmp_path
    )

    assert offenders == [
        "apps/synthetic/src/thing.py imports lunaris_live (lunaris-live), not declared"
    ], offenders


def test_the_checker_stays_quiet_when_the_import_is_declared(tmp_path: Path) -> None:
    """The same app, with the declaration present, must report nothing.

    Pins the other direction so the checker cannot be "fixed" into always failing — and proves the
    line above fires on the *declaration*, not merely on the presence of an import.
    """
    app_dir = _write_synthetic_app(tmp_path, declares='"lunaris-live"', imports="lunaris_live")

    assert (
        undeclared_workspace_imports(app_dir, {"lunaris_live": "lunaris-live"}, root=tmp_path) == []
    )


def test_the_checker_ignores_third_party_imports(tmp_path: Path) -> None:
    """A third-party import is uv's to resolve, not this check's to police.

    Reported as an offender it would be noise, and a check that cries wolf is a check somebody
    switches off.
    """
    app_dir = _write_synthetic_app(tmp_path, declares="", imports="httpx")

    assert (
        undeclared_workspace_imports(app_dir, {"lunaris_live": "lunaris-live"}, root=tmp_path) == []
    )


def test_the_checker_ignores_a_member_importing_itself(tmp_path: Path) -> None:
    """A package needs no manifest entry for its own top-level package.

    The synthetic app goes in its own directory rather than reusing ``tmp_path`` directly, because
    ``_write_synthetic_app`` always writes to ``<root>/apps/synthetic`` and a second call on the
    same root would collide with the app the sibling tests wrote.
    """
    own = _write_synthetic_app(tmp_path / "own", declares="", imports="synthetic_app")

    assert (
        undeclared_workspace_imports(own, {"synthetic_app": "synthetic-app"}, root=tmp_path / "own")
        == []
    )


def test_the_closure_check_actually_reads_sources_and_manifests() -> None:
    """Guard the guard.

    Every assertion above is of the form "found nothing wrong", which is also what a silently broken
    sweep reports. This pins that the mapping, the source discovery and the declaration parser each
    return real content — so the check cannot pass by finding nothing to check.
    """
    mapping = _import_name_to_distribution()
    assert mapping.get("lunaris_live") == "lunaris-live", (
        f"the import→distribution map should cover Live; got {mapping.get('lunaris_live')!r}"
    )
    assert mapping.get("lunaris_runtime") == "lunaris-runtime"
    assert len(mapping) >= 6, f"expected the workspace's packages, found {len(mapping)}"

    sources = _shipped_sources(REPO_ROOT / "apps/api")
    assert len(sources) > 50, f"expected to sweep the API's sources, found {len(sources)}"
    app_module = REPO_ROOT / "apps/api/src/lunaris_api/app.py"
    assert app_module in sources, "the sweep must cover the module that mounts every router"
    assert "lunaris_live" in imported_top_level_packages(
        REPO_ROOT / "apps/api/src/lunaris_api/live/router.py"
    ), "the import extractor should see Live's router naming lunaris_live"

    declared = _declared_dependencies(REPO_ROOT / "apps/api")
    assert "fastapi" in declared, "the declaration parser should strip version specifiers"
    assert "lunaris-video" in declared, "the declaration parser should strip extras"
