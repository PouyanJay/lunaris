from importlib import resources
from importlib.resources.abc import Traversable


def _pinned_root() -> Traversable:
    return resources.files("lunaris_video") / "skill" / "pinned"


def _walk(node: Traversable, prefix: str) -> list[str]:
    names: list[str] = []
    for child in node.iterdir():
        path = f"{prefix}{child.name}"
        if child.is_dir():
            names.extend(_walk(child, f"{path}/"))
        else:
            names.append(path)
    return names


def read_skill_asset(name: str) -> str:
    """The text of one pinned skill file, by spec-relative name (e.g. ``references/qa-gates.md``).

    The pinned copy vendored here is the runtime's ONLY source of the skill — `.claude/` is
    gitignored and never ships, so prompt context (patterns, checklists, schema spec) must come
    from package data. Verbatim-ness is enforced by the fingerprint test, not by trust.
    """
    asset = _pinned_root()
    for part in name.split("/"):
        asset = asset / part
    return asset.read_text(encoding="utf-8")


def skill_asset_names() -> list[str]:
    """Every pinned file's spec-relative name — the pin test audits this set exactly."""
    return sorted(_walk(_pinned_root(), ""))
