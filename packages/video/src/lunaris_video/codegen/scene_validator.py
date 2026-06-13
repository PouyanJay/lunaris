import re

from lunaris_video.schemas import SceneContract

# The no-LaTeX rule and the CE-only rule, enforced deterministically — a completion that
# violates them is rejected BEFORE any subprocess runs, with the violation named so the repair
# turn can fix it. `include_numbers` is banned outright: Axes numbers secretly invoke LaTeX.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(MathTex|Tex|SingleStringMathTex|BulletedList|Title)\s*\("), "LaTeX mobject"),
    (re.compile(r"include_numbers"), "Axes numbers (secretly LaTeX)"),
    (re.compile(r"\bmanimlib\b|\bmanimgl\b"), "manimgl import (CE only)"),
]

_CODE_FENCE = re.compile(r"^```(?:python)?\s*\n|\n```\s*$", re.MULTILINE)
# A sane upper bound on a single scene's source — the model's context already bounds it; this is
# defense-in-depth against a degenerate completion making compile() chew unbounded CPU.
_MAX_SOURCE_CHARS = 200_000


def validate_scene_source(completion: str, scene: SceneContract) -> str:
    """A CORRECTNESS gate on generated source (no-LaTeX/CE-only/parses); NOT a security boundary.

    ``compile()`` parses but never executes, so this cannot stop hostile runtime behaviour —
    ``import os; os.system(...)`` passes it and then runs under ``manim render``. The trust
    boundary is the subprocess sandbox (``run_sandboxed``), not this function. Public because
    Gate A's tests and the security review reason about it directly.
    """
    if len(completion) > _MAX_SOURCE_CHARS:
        raise ValueError(f"scene source exceeds {_MAX_SOURCE_CHARS} chars")
    source = _CODE_FENCE.sub("", completion).strip() + "\n"
    for pattern, label in _FORBIDDEN_PATTERNS:
        match = pattern.search(source)
        if match:
            raise ValueError(f"forbidden construct ({label}): {match.group(0)!r}")
    if "from style_tokens import" not in source:
        raise ValueError("missing `from style_tokens import *` — tokens must come from the map")
    class_pattern = re.compile(rf"class\s+{re.escape(scene.scene_class_name)}\s*\(")
    if not class_pattern.search(source):
        raise ValueError(f"missing scene class {scene.scene_class_name}(Scene)")
    try:
        compile(source, f"{scene.id}.py", "exec")
    except SyntaxError as exc:
        raise ValueError(f"source does not parse: {exc}") from exc
    return source
