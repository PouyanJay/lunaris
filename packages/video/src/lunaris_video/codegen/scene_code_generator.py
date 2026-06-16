import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

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
  helpers (title_bar, make_array, hand_axes, smooth_curve, pivot_anchor, hero_title,
  make_network, clear_scene) from style_tokens — never hardcode colors or fonts.
- Implement every beat in order. Each beat's animations and waits MUST sum to EXACTLY its
  on-screen window from BEAT TIMING below — the narration is synced to these durations.
- Any group that rotates or orbits needs an explicit pivot anchor (pivot_anchor helper) —
  never rotate about get_center() of an asymmetric group.
- End the scene by fading out all mobjects (clear_scene(self)) for clean concat boundaries.
- The scene is EXACTLY its beats (each filling its window) followed by that one clear_scene(self).
  Put NO self.wait(), self.play() or pause OUTSIDE a beat — its narration audio matches the beats
  plus that closing fade, so any extra time makes the render longer than its audio and desyncs it.

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

{literal_rules}
{archetype_guidance}
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

SYNC — the element the narration names must be ON SCREEN by each beat's MIDPOINT (a sync gate
samples the frame there and rejects a beat whose narrated thing is not yet shown). So:
- FRONT-LOAD every reveal: play the FadeIn/Create/Write/Transform of the thing the words name in
  the FIRST part of the beat (well under half its window), then HOLD it for the rest. Never put the
  named element in the tail of the window — at the midpoint it would still be missing.
- If a beat narrates motion, run the motion at the START of the window and hold at the end, so the
  words land while it is happening, not after it has stopped.
- The beat() helper already holds at the end: pass the reveal anims FIRST with short run_times so
  the trailing hold — and thus the on-screen presence — covers the midpoint.

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

# The codegen parse failures seen most on prod, stated as rules. Front-loaded into GENERATE so the
# first render already parses, and restated by the format-repair turn (the base render/visual/sync
# repair templates don't carry it) so a parse-class rejection from any path gets the rules to
# self-correct. ASCII-only on purpose (the section is itself the example): backslashes are escaped
# (\\n) so the prompt shows the literal \n / \t / \\ escapes, and no smart punctuation leaks into a
# prompt about ASCII.
_VALID_LITERALS = """\
VALID PYTHON LITERALS (the most common codegen parse failures: get these right the first time)
- Strings: straight ASCII quotes only (" or '), never smart/curly quotes. CLOSE every quote on the
  SAME line; a quoted string must never span lines or be left open (an unterminated string literal
  is the #1 parse failure). For a line break inside a string write the two characters \\n; build a
  long message from adjacent pieces ("part one " "part two"), never a bare line-spanning string.
- Numbers: write decimals with a digit on BOTH sides of the point (0.5 and 5.0, never .5 or 5.); put
  an operator between a number and a name (2 * x, never 2x); no commas or stray characters inside a
  numeric literal.
- Backslashes: the only backslash allowed is a valid string escape (\\n, \\t, \\\\); never leave a
  stray backslash in code."""

_FORMAT_REPAIR_TEMPLATE = (
    "\n\nYour previous reply was rejected before rendering: {error}\n"
    + _VALID_LITERALS
    + "\nRespond again with ONLY the corrected, complete Python source for the scene file."
)

# The two stubborn Gate-B archetypes get targeted guidance — front-loaded into GENERATE so the first
# render is already clean, and repeated at REPAIR as the safety net. Every other archetype carries
# neither (the prompt stays focused on the scene's own contract).
#
# Hook/title: one big headline on a near-empty frame, so the failures are overflow / low contrast /
# overlap, not diagram problems.
_HOOK_TITLE_BUILD = """\
- HOOK / TITLE scene: build the card from hero_title(headline, subtitle, kicker) — it scales the
  headline to the frame and centers the group, so the title can never overflow the edges or sit
  off-centre (the two defects these scenes fail on). Headline in INK (at most one ACCENT word),
  subtitle in MUTED; never hand-place Text or Transform one title onto another."""
_HOOK_TITLE_REPAIR = """\
THIS IS A HOOK / TITLE scene — the spatial defects these archetypes fail on most; fix them directly:
- OVERFLOW is the #1 failure: build the card from hero_title(...) (it runs
  scale_to_fit_width on the headline for you), or scale_to_fit_width(headline, config.frame_width -
  1.0) BEFORE you animate it — never let big text clip the frame edges.
- LOW CONTRAST: a title reads in INK (or ACCENT for one emphasized word) on the background; a
  subtitle in MUTED. Never a low-contrast hue that fails a squint test.
- OVERLAP / CENTERING: stack title + subtitle/kicker in a VGroup(...).arrange(DOWN, buff=0.4) and
  center the group; never Transform one title onto another — FadeOut then FadeIn."""

# Network/graph: a "web of nodes" whose ad-hoc coordinates cram into one side, half-formed.
_NETWORK_BUILD = """\
- NETWORK / GRAPH scene (a "web of nodes", neural net, or pipeline): build it from
  make_network(layer_sizes) — it lays the nodes out in fit-to-frame columns and wires them, so the
  graph can never cram into one side. Reveal it LAYER BY LAYER across the beats (never Create the
  whole graph at once); keep ~6 nodes per layer and summarize a bigger network rather than drawing
  every unit."""
_NETWORK_REPAIR = """\
THIS IS A NETWORK / GRAPH scene — fix the crammed-tangle defects these fail on:
- Replace any hand-placed node coordinates with make_network(layer_sizes): it lays the nodes out in
  fit-to-frame columns and wires them, centred — so they cannot pack into one side or overflow.
- Reveal the graph LAYER BY LAYER (Create one column + its incoming edges at a time), never the
  whole tangle at once; cap ~6 nodes per layer and summarize a bigger network."""


@dataclass(frozen=True)
class _ArchetypeGuidance:
    # Targeted guidance for one stubborn archetype, with its GENERATE-time "build it clean" hint and
    # REPAIR-time "fix these defects" hint. ``archetype_markers`` match anywhere in the scene's
    # declared archetype (the planner's visual-form decision — the authoritative signal); the looser
    # ``slug_markers`` match only as WHOLE words of the scene id, so a body scene like
    # "S3_intro_to_backprop" or "S4_graph_traversal" does not pick up title/network guidance.
    archetype_markers: tuple[str, ...]
    slug_markers: tuple[str, ...]
    build: str
    repair: str


_ARCHETYPE_GUIDANCE: tuple[_ArchetypeGuidance, ...] = (
    # Hook/title is a narrative position, not a taxonomy archetype, so it keys off the slug; "intro"
    # is deliberately excluded (too many "S3_intro_to_X" body scenes). Network/graph IS a taxonomy
    # archetype, so it keys off the declared archetype only — never the slug, where "graph" collides
    # with graph-algorithm content scenes.
    _ArchetypeGuidance(("hook", "title"), ("hook", "title"), _HOOK_TITLE_BUILD, _HOOK_TITLE_REPAIR),
    _ArchetypeGuidance(("network", "graph", "neural"), (), _NETWORK_BUILD, _NETWORK_REPAIR),
)


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
            literal_rules=_VALID_LITERALS,
            archetype_guidance=_generate_archetype_guidance(scene),
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


def _selected_guidance(scene: SceneContract) -> list[_ArchetypeGuidance]:
    # The stubborn-archetype guidance that applies to this scene: an archetype-substring match (the
    # authoritative visual-form signal) OR a whole-word slug match (so "graph" / "intro" inside a
    # body scene's id can't misfire). See _ArchetypeGuidance for why the two are separate.
    archetype = scene.archetype.lower()
    slug_words = set(re.split(r"[^a-z0-9]+", scene.id.lower()))
    return [
        g
        for g in _ARCHETYPE_GUIDANCE
        if any(m in archetype for m in g.archetype_markers)
        or any(m in slug_words for m in g.slug_markers)
    ]


def _generate_archetype_guidance(scene: SceneContract) -> str:
    # GENERATE-time guidance, front-loaded so the first render of a stubborn archetype is already
    # clean — empty (no section at all) for every other scene.
    selected = _selected_guidance(scene)
    if not selected:
        return ""
    hints = "\n".join(g.build for g in selected)
    return f"\nARCHETYPE GUIDANCE (stubborn archetype — build it clean the first time):\n{hints}\n"


def _archetype_hint(scene: SceneContract) -> str:
    # REPAIR-time guidance for the archetypes Gate B fails on most — empty for every other scene, so
    # the visual-repair prompt only carries it when the scene actually is one of them. The trailing
    # newline keeps a blank line before BEAT TIMING in the repair template.
    selected = _selected_guidance(scene)
    return "\n".join(g.repair for g in selected) + "\n" if selected else ""


def _format_defects(defects: list[QaDefect]) -> str:
    return "\n".join(
        f"{n}. {defect.issue} — fix: {defect.fix_hint}" for n, defect in enumerate(defects, 1)
    )


def _format_timing(timing: SceneTiming) -> str:
    return "\n".join(f"- {beat.id}: {beat.anim_s}s" for beat in timing.beats)
