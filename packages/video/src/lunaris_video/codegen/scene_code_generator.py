import re
from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.schemas import SceneContract
from lunaris_video.skill import read_skill_asset

_logger = structlog.get_logger(__name__)

# The no-LaTeX rule and the CE-only rule, enforced deterministically — a completion that
# violates them is rejected BEFORE any subprocess runs, with the violation named so the repair
# turn can fix it. `include_numbers` is banned outright: Axes numbers secretly invoke LaTeX.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(MathTex|Tex|SingleStringMathTex|BulletedList|Title)\s*\("), "LaTeX mobject"),
    (re.compile(r"include_numbers"), "Axes numbers (secretly LaTeX)"),
    (re.compile(r"\bmanimlib\b|\bmanimgl\b"), "manimgl import (CE only)"),
]

_CODE_FENCE = re.compile(r"^```(?:python)?\s*\n|\n```\s*$", re.MULTILINE)

_GENERATE_TEMPLATE = """\
You are the CODE stage of an explainer-video pipeline. Implement ONE Manim Community Edition
scene, exactly as its contract specifies.

SCENE CONTRACT (JSON)
{scene_json}

COURSE TOPIC: {topic}

HARD RULES (violations are rejected automatically)
- Manim Community Edition only — never manimgl/manimlib.
- NO LaTeX anywhere: never MathTex, Tex, Title, BulletedList, or Axes with include_numbers.
  Use Text() for all text; hand-roll axes from Line + Text (helpers below).
- Start the file with exactly:
    from manim import *
    from style_tokens import *
- Define exactly one class: `class {scene_class_name}(Scene):` with a `construct` method.
- Use the style tokens (BG, INK, MUTED, ACCENT, DANGER, GREEN, PANEL, ALT, FONT) and the
  helpers (title_bar, make_array, hand_axes, smooth_curve, pivot_anchor, clear_scene) from
  style_tokens — never hardcode colors or fonts.
- Implement every beat in order; honor each beat's min_visual_s as a minimum on-screen time.
- Any group that rotates or orbits needs an explicit pivot anchor (pivot_anchor helper) —
  never rotate about get_center() of an asymmetric group.
- End the scene by fading out all mobjects (clear_scene(self)) for clean concat boundaries.

PATTERNS REFERENCE (verbatim from the pinned skill — follow it)
{patterns}

OUTPUT
Respond with ONLY the Python source for this one scene file — no prose, no code fences."""

_REPAIR_RENDER_TEMPLATE = """\
You are repairing a Manim CE scene that FAILED TO RENDER. Fix the failure with the smallest
change that preserves the contract; do not redesign the scene.

SCENE CONTRACT (JSON)
{scene_json}

CURRENT SOURCE (failing)
{source}

RENDER FAILURE (stack trace / stderr tail)
{error_tail}

The HARD RULES still apply: CE only; no LaTeX (no MathTex/Tex/Title/BulletedList/include_numbers);
`from manim import *` and `from style_tokens import *`; exactly one class
`class {scene_class_name}(Scene):`; tokens/helpers from style_tokens; fade out everything at the
end. Respond with ONLY the corrected, complete Python source — no prose, no code fences."""

_FORMAT_REPAIR_TEMPLATE = """

Your previous reply was rejected before rendering: {error}
Respond again with ONLY the corrected, complete Python source for the scene file."""


class SceneCodeGenerator:
    """The CODE stage: one contract scene → one Manim source file (and its render repairs).

    Completions pass a deterministic validation (syntax, required class, no-LaTeX rule, style
    import) with bounded format-repair turns; render-time failures come back through
    ``repair`` with the stack-trace tail folded in (Gate A's loop). The model seam is the same
    plain async completion callable the planner uses.
    """

    def __init__(self, *, invoke: Callable[[str], Awaitable[str]]) -> None:
        self._invoke = invoke
        # The pinned patterns reference is immutable; read it once at construction so codegen
        # never touches the filesystem on the hot path.
        self._patterns = read_skill_asset("references/manim-patterns.md")

    async def generate(self, scene: SceneContract, *, topic: str) -> str:
        prompt = _GENERATE_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            topic=topic,
            scene_class_name=scene.scene_class_name,
            patterns=self._patterns,
        )
        source = await self._complete(prompt, scene)
        _logger.info("scene_codegen.generated", scene_id=scene.id, chars=len(source))
        return source

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str:
        prompt = _REPAIR_RENDER_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            source=source,
            error_tail=error_tail,
            scene_class_name=scene.scene_class_name,
        )
        repaired = await self._complete(prompt, scene)
        _logger.info("scene_codegen.repaired", scene_id=scene.id, chars=len(repaired))
        return repaired

    async def _complete(self, prompt: str, scene: SceneContract) -> str:
        def parse(text: str) -> str:
            return validate_scene_source(text, scene)

        return await invoke_with_parse_repair(
            self._invoke,
            prompt,
            parse,
            repair_instruction=_FORMAT_REPAIR_TEMPLATE,
        )


def validate_scene_source(completion: str, scene: SceneContract) -> str:
    """Deterministic gate on generated source; returns the cleaned code or raises ValueError.

    Public because Gate A's tests and the security review reason about it directly: this is
    the line where the no-LaTeX rule stops being a prompt suggestion and becomes structure.
    """
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
