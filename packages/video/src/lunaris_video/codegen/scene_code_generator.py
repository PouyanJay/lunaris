from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.codegen.scene_validator import validate_scene_source
from lunaris_video.schemas import QaDefect, SceneContract, SceneTiming
from lunaris_video.skill import read_skill_asset

_logger = structlog.get_logger(__name__)

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
- Implement every beat in order. Each beat's animations and waits MUST sum to EXACTLY its
  on-screen window from BEAT TIMING below — the narration is synced to these durations.
- Any group that rotates or orbits needs an explicit pivot anchor (pivot_anchor helper) —
  never rotate about get_center() of an asymmetric group.
- End the scene by fading out all mobjects (clear_scene(self)) for clean concat boundaries.

LAYOUT & LEGIBILITY (the spatial defects Gate B rejects — get these right the first time)
- ONE Text per value. Never stack, overlap, or Transform one Text onto another in the same spot —
  if a value changes, FadeOut the old Text before FadeIn the new one. Overlapping text is the #1
  rejected defect.
- High contrast always: text on a filled shape uses a colour that clearly reads against that fill
  (INK on dark PANEL/box fills; never a low-contrast hue like GREEN on a light/ALT fill). A
  hash/number/label must pass a squint test.
- On-screen data must EXACTLY match the beat narration: if the narration says the same input gives
  the SAME hash, show the identical string both times; never invent a different value.
- Every label must be next_to a mobject that is actually on screen at that moment — if you label
  an "input", draw the input object; an unattached label reading into empty space is rejected.
- Size for the frame: scale_to_fit_width any text that might overflow its box BEFORE animating it.

BEAT TIMING (audio-drives-video — these on-screen windows are FIXED; the narration is timed to them)
Each beat's animations and waits must sum to EXACTLY its window in seconds:
{timing}
Never let a beat drift from its window — the audio is synced to these exact durations. Put this
helper at the top of construct() and drive each beat through it so the totals are exact:
    def beat(anims, total):
        used = 0.0
        for anim, run_time in anims:
            self.play(anim, run_time=run_time)
            used += run_time
        self.wait(max(0.05, total - used))

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

BEAT TIMING (unchanged — each beat's animations + waits must still sum to EXACTLY its window):
{timing}

The HARD RULES still apply: CE only; no LaTeX (no MathTex/Tex/Title/BulletedList/include_numbers);
`from manim import *` and `from style_tokens import *`; exactly one class
`class {scene_class_name}(Scene):`; tokens/helpers from style_tokens; fade out everything at the
end. Respond with ONLY the corrected, complete Python source — no prose, no code fences."""

_REPAIR_VISUAL_TEMPLATE = """\
You are repairing a Manim CE scene that RENDERS but is VISUALLY WRONG. The visual-QA gate looked
at frames and found spatial defects. Fix EACH defect with the smallest targeted edit; do not
redesign the scene or change its narration.

SCENE CONTRACT (JSON)
{scene_json}

CURRENT SOURCE (renders, but visually defective)
{source}

DEFECTS FOUND (fix every one)
{defects}
{archetype_hint}
BEAT TIMING (unchanged — keep each beat's animations + waits summing to EXACTLY its window):
{timing}

Common spatial fixes (from the pinned patterns): rotate groups about an explicit pivot anchor,
not get_center(); keep labels next_to their object across Transforms; compute max extent vs a
container BEFORE animating growth; span baselines/axes across every element. The HARD RULES still
apply: CE only; no LaTeX; `from manim import *` and `from style_tokens import *`; exactly one class
`class {scene_class_name}(Scene):`; tokens/helpers from style_tokens; fade out everything at the
end. Respond with ONLY the corrected, complete Python source — no prose, no code fences."""

_REPAIR_SYNC_TEMPLATE = """\
You are repairing a Manim CE scene whose narration and visuals are OUT OF SYNC. The sync gate
extracted the frame at a narrated beat's MIDPOINT and the element the words describe was not on
screen yet. Fix the TIMING of this beat so the narrated element is on screen by its midpoint; do not
redesign the scene, change any narration, or touch any other beat.

SCENE CONTRACT (JSON)
{scene_json}

CURRENT SOURCE (renders, but this beat desyncs)
{source}

DESYNCED BEAT
beat {beat_id}: {reason}

THE FIX (from the pinned narration-sync guide)
- Move the reveal of the named element to the START of this beat's window: play its
  FadeIn/Create/Write/Transform FIRST, then HOLD it (self.wait) the rest of the window. The thing
  the words name must be fully on screen by the beat's MIDPOINT — never introduced in the tail.
- If the beat narrates motion, put the motion at the START of the window and the static hold at the
  end, so the words describing the motion land while it is happening, not after it has stopped.
- Keep every other beat exactly as it is — only this beat's internal ordering changes.

BEAT TIMING (unchanged — each beat's animations + waits must still sum to EXACTLY its window):
{timing}

The HARD RULES still apply: CE only; no LaTeX (no MathTex/Tex/Title/BulletedList/include_numbers);
`from manim import *` and `from style_tokens import *`; exactly one class
`class {scene_class_name}(Scene):`; tokens/helpers from style_tokens; fade out everything at the
end. Respond with ONLY the corrected, complete Python source — no prose, no code fences."""

_FORMAT_REPAIR_TEMPLATE = """

Your previous reply was rejected before rendering: {error}
Respond again with ONLY the corrected, complete Python source for the scene file."""

# Hook/title scenes are the stubborn Gate-B failures: one big headline on a near-empty frame, so the
# usual defects are overflow / low contrast / overlap, not diagram problems. When a defective scene
# is one of these archetypes, the visual-repair prompt gets this extra, targeted guidance.
_HOOK_TITLE_HINT = """\
THIS IS A HOOK / TITLE scene — the spatial defects these archetypes fail on most; fix them directly:
- OVERFLOW is the #1 failure: scale_to_fit_width(headline, config.frame_width - 1.0) BEFORE you
  animate it, and wrap or shorten a long title — never let big text clip the frame edges.
- LOW CONTRAST: a title reads in INK (or ACCENT for one emphasized word) on the background; a
  subtitle in MUTED. Never a low-contrast hue that fails a squint test.
- OVERLAP / CENTERING: stack title + subtitle/kicker in a VGroup(...).arrange(DOWN, buff=0.4) and
  center the group; never Transform one title onto another in the same spot — FadeOut then FadeIn.
"""
# Slugs/archetypes that mark a scene as a hook/title card (matched case-insensitively).
_HOOK_TITLE_MARKERS = ("hook", "title", "intro")


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

    async def generate(self, scene: SceneContract, *, topic: str, timing: SceneTiming) -> str:
        prompt = _GENERATE_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            topic=topic,
            scene_class_name=scene.scene_class_name,
            timing=_format_timing(timing),
            patterns=self._patterns,
        )
        source = await self._complete(prompt, scene)
        _logger.info("scene_codegen.generated", scene_id=scene.id, chars=len(source))
        return source

    async def repair(
        self, scene: SceneContract, *, source: str, error_tail: str, timing: SceneTiming
    ) -> str:
        prompt = _REPAIR_RENDER_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            source=source,
            error_tail=error_tail,
            timing=_format_timing(timing),
            scene_class_name=scene.scene_class_name,
        )
        repaired = await self._complete(prompt, scene)
        _logger.info("scene_codegen.repaired", scene_id=scene.id, chars=len(repaired))
        return repaired

    async def repair_visual(
        self, scene: SceneContract, *, source: str, defects: list[QaDefect], timing: SceneTiming
    ) -> str:
        prompt = _REPAIR_VISUAL_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            source=source,
            defects=_format_defects(defects),
            archetype_hint=_archetype_hint(scene),
            timing=_format_timing(timing),
            scene_class_name=scene.scene_class_name,
        )
        repaired = await self._complete(prompt, scene)
        _logger.info(
            "scene_codegen.visual_repaired",
            scene_id=scene.id,
            defect_count=len(defects),
            chars=len(repaired),
        )
        return repaired

    async def repair_sync(
        self, scene: SceneContract, *, source: str, beat_id: str, reason: str, timing: SceneTiming
    ) -> str:
        prompt = _REPAIR_SYNC_TEMPLATE.format(
            scene_json=scene.model_dump_json(indent=2),
            source=source,
            beat_id=beat_id,
            reason=reason,
            timing=_format_timing(timing),
            scene_class_name=scene.scene_class_name,
        )
        repaired = await self._complete(prompt, scene)
        _logger.info(
            "scene_codegen.sync_repaired", scene_id=scene.id, beat_id=beat_id, chars=len(repaired)
        )
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


def _archetype_hint(scene: SceneContract) -> str:
    # Extra repair guidance for the archetypes Gate B fails on most — empty for every other scene,
    # so the visual-repair prompt only carries the hook/title hint when it is actually a hook/title.
    haystack = f"{scene.id} {scene.archetype}".lower()
    return _HOOK_TITLE_HINT if any(m in haystack for m in _HOOK_TITLE_MARKERS) else ""


def _format_defects(defects: list[QaDefect]) -> str:
    return "\n".join(
        f"{n}. {defect.issue} — fix: {defect.fix_hint}" for n, defect in enumerate(defects, 1)
    )


def _format_timing(timing: SceneTiming) -> str:
    return "\n".join(f"- {beat.id}: {beat.anim_s}s" for beat in timing.beats)
