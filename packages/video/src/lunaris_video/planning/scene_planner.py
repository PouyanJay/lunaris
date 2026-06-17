import math
from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair
from lunaris_runtime.schema import VideoKind
from lunaris_runtime.video_build import target_seconds_for

from lunaris_video.models.grounding_packet import GroundingPacket
from lunaris_video.models.lesson_source import LessonSource
from lunaris_video.models.sibling_contract_digest import SiblingContractDigest
from lunaris_video.schemas import (
    FRAMING_ONLY_SENTINEL,
    ChapteredContractDraft,
    ChapteredSceneContracts,
    ContractDraft,
    SceneContract,
    SceneContracts,
)
from lunaris_video.skill import read_skill_asset
from lunaris_video.style import video_global_style

_logger = structlog.get_logger(__name__)

# A chaptered video runs roughly one chapter per started minute (each chapter is 3-4 scenes inside
# the skill's validated envelope); at least two, so "chaptered" always means more than one chapter.
_SECONDS_PER_CHAPTER = 60

# C1 complexity budget: the most distinct on-screen objects one scene's ``objects`` list may name. A
# scene over this renders as a crammed tangle (the binary-search / neural-net "web of nodes"
# failures). Enforced post-parse — an over-budget contract earns a repair turn so the model splits
# the scene or reveals incrementally — the prompt's "~10 at once" guidance was not binding enough.
MAX_SCENE_OBJECTS = 10

_PROMPT_TEMPLATE = """\
You are the PLAN stage of an explainer-video pipeline. Turn ONE lesson into scene contracts —
the complete storyboard a coder who never saw the lesson could implement. This stage sets the
quality ceiling: spend your thinking here.

LESSON
- Course topic: {course_topic}
- Lesson: {lesson_title}
- Audience: {audience}
- Lesson text (narrative context for phrasing only — the facts you may assert are the verified
  claims below, NOT whatever the prose happens to say), between the markers:
--- LESSON TEXT START ---
{prose}
--- LESSON TEXT END ---
{upstream_context}
ENVELOPE
- 3 to 5 scenes, each 15-30 seconds; total duration about {target_seconds} seconds.
- Standard arc: problem/hook -> key insight -> mechanism step-by-step -> consequence -> verdict.
- 3-6 beats per scene. Each beat is an object with: id ("b1", "b2", ...), action (what happens
  visually), narration (the exact self-contained clause(s) spoken DURING that action; write for
  the ear, about 2.4 words per second), and min_visual_s (a float floor so fast speech cannot
  rush the visual; REQUIRED when narration is the empty string).
- ONE reveal per beat: each beat introduces ONE new visual element or state, named in its narration.
  If a clause introduces two ("the network, THEN the loss"), SPLIT it into two beats. The renderer
  front-loads each beat's reveal to the start of its window, so a beat that introduces a second
  element midway would not be on screen when its words are spoken (it would desync).
- Scene ids match S<N>_<slug> (e.g. "S1_problem"); slugs are lowercase snake_case.
- Assign each scene exactly one primary archetype from the reference below; compose at most two.
  Never invent a free-form visual when an archetype fits.
- COMPLEXITY BUDGET (enforced): each scene's "objects" list names at most {max_objects} distinct
  on-screen objects — a downstream check REJECTS any scene over the limit and makes you re-plan it.
  A scene with more than {max_objects} objects renders as a crammed tangle: SPLIT an over-budget
  scene into two simpler scenes, and reveal a bigger structure (a wide network, a long pipeline)
  incrementally across its beats — one layer or step per beat — never all at once. Use the
  network/graph archetype for any "nodes wired together" visual (network or neural net).
- Find the one inspired beat: one scene where the visual's FORM carries the argument. If every
  scene is a generic template fill, revise before answering.

GROUNDING (this pipeline stage has no research access — the verified claims are the ONLY facts you
may assert; a downstream gate diffs every on-screen number and comparison against them)
{grounding_block}
- Per scene, set "sources" to the list of claim ids the scene draws its facts from (e.g.
  ["c1", "c3"]), or to ["{framing_sentinel}"] for a scene that states no empirical facts.
- State a number, ranking or comparison ONLY if it appears verbatim in a claim the scene cites.
  Never invent a figure, and never cite a claim id that is not listed above.
{regenerate_directive}
ARCHETYPE REFERENCE (verbatim from the pinned skill)
{archetypes}

OUTPUT
Respond with ONLY one JSON object — no prose, no code fences — with EXACTLY these fields:
  "topic": string, "audience": string, "visual_archetypes_used": [strings],
  "asset_strategy": string (e.g. "tier-a procedural"), "scenes": [scene objects as specified:
  id, archetype, narration (full spoken script, the beats' narrations joined), objects
  (semantic on-screen object list), beats, sources, duration_s].
Do NOT include global_style, voice, or verifier_gates — the system injects those."""

_REPAIR_TEMPLATE = """

Your previous reply could not be used: {error}
Respond again with ONLY the corrected JSON object, exactly as specified above."""

_NO_CLAIMS_BLOCK = (
    "- No verified claims are available for this lesson, so EVERY scene must be framing only: set "
    f'its "sources" to ["{FRAMING_ONLY_SENTINEL}"] and state no numbers, rankings or comparisons.'
)

# The "Simpler" regenerate directive (V6-T2): steer PLAN toward the fewest, plainest scenes when a
# prior version was too complex or failed quality checks. Injected into the {regenerate_directive}
# slot; empty for an ordinary plan. The leading newline keeps the section spaced from the grounding
# block above it.
_SIMPLER_DIRECTIVE = """
REGENERATE — SIMPLER (a prior version was too complex or failed quality checks; make this one
plainer):
- Plan the FEWEST scenes that still tell the arc (prefer 2-3, never more than 4).
- Use ONLY the plainest archetypes — a title card, a single labelled diagram, one focused
  comparison. Avoid dense multi-part mechanisms and busy composite scenes.
- Fewer beats per scene; one idea per scene. Clarity over completeness.
"""

_CHAPTERED_PROMPT_TEMPLATE = """\
You are the PLAN stage of an explainer-video pipeline. Turn this topic into a CHAPTERED overview
video — a continuous {target_seconds}-second tour that opens a course. It is longer than a single
explainer, so it is organized into chapters; the chapters concatenate into ONE MP4.

TOPIC
- Course topic: {course_topic}
- This video: {unit_title}
- Audience: {audience}
- Framing notes (for the arc and phrasing only — the facts you may assert are the verified claims
  below, NOT whatever this text happens to say), between the markers:
--- FRAMING START ---
{prose}
--- FRAMING END ---

ENVELOPE
- Organize into about {chapter_count} chapters; give each a short title and 3 to 4 scenes.
- Each scene is 15-25 seconds; the whole video totals about {target_seconds} seconds.
- Each chapter stays inside the skill's validated 3-to-5-scene envelope; together the chapters tell
  one arc: what the topic is -> why it matters -> where the course takes you.
- 3-6 beats per scene. Each beat is an object with: id ("b1", "b2", ...), action (what happens
  visually), narration (the exact self-contained clause(s) spoken DURING that action; write for the
  ear, about 2.4 words per second), and min_visual_s (a float floor so fast speech cannot rush the
  visual; REQUIRED when narration is the empty string).
- ONE reveal per beat: each beat introduces ONE new visual element or state, named in its narration.
  If a clause introduces two ("the network, THEN the loss"), SPLIT it into two beats. The renderer
  front-loads each beat's reveal to the start of its window, so a beat that introduces a second
  element midway would not be on screen when its words are spoken (it would desync).
- Scene ids match S<N>_<slug> and are UNIQUE across the WHOLE video (not per chapter); slugs are
  lowercase snake_case. Chapter ids are "ch1", "ch2", ....
- Assign each scene exactly one primary archetype from the reference below; compose at most two.
- COMPLEXITY BUDGET (enforced): each scene's "objects" list names at most {max_objects} distinct
  on-screen objects — a downstream check REJECTS any scene over the limit and makes you re-plan it.
  A scene with more than {max_objects} objects renders as a crammed tangle: SPLIT an over-budget
  scene into two simpler scenes, and reveal a bigger structure (a wide network, a long pipeline)
  incrementally across its beats — one layer or step per beat — never all at once. Use the
  network/graph archetype for any "nodes wired together" visual (network or neural net).

GROUNDING (this pipeline stage has no research access — the verified claims are the ONLY facts you
may assert; a downstream gate diffs every on-screen number and comparison against them)
{grounding_block}
- Per scene, set "sources" to the list of claim ids the scene draws its facts from (e.g.
  ["c1", "c3"]), or to ["{framing_sentinel}"] for a scene that states no empirical facts.
- State a number, ranking or comparison ONLY if it appears verbatim in a claim the scene cites.
  Never invent a figure, and never cite a claim id that is not listed above.
{regenerate_directive}
ARCHETYPE REFERENCE (verbatim from the pinned skill)
{archetypes}

OUTPUT
Respond with ONLY one JSON object — no prose, no code fences — with EXACTLY these fields:
  "topic": string, "audience": string, "visual_archetypes_used": [strings],
  "asset_strategy": string (e.g. "tier-a procedural"), "chapters": [ {{"id": string, "title":
  string, "scenes": [scene objects as specified: id, archetype, narration (full spoken script, the
  beats' narrations joined), objects (semantic on-screen object list), beats, sources, duration_s]}}
  ].
Do NOT include global_style, voice, or verifier_gates — the system injects those."""

_NO_CLAIMS_BLOCK_CHAPTERED = (
    "- No verified claims are available for this video, so EVERY scene must be framing only: set "
    f'its "sources" to ["{FRAMING_ONLY_SENTINEL}"] and state no numbers, rankings or comparisons.'
)


class ScenePlanner:
    """The PLAN node: a video source in, a validated contract out (plan §1.2).

    ``plan`` produces a flat ``SceneContracts`` (lesson + summary); ``plan_chaptered`` produces a
    ``ChapteredSceneContracts`` for the longer overview (V5-T1). In both, the model emits a draft of
    everything creative; the system injects what is not the model's to decide — ``global_style``
    from the enterprise-ui token map and the spec's verifier gates — and lets the model pick *which*
    verified claims a scene cites (never invent figures), rejecting any draft that cites a claim id
    the packet does not list. ``invoke`` is the package's only model seam (a plain async text
    completion), so the planner is testable with a scripted stub and the composition root chooses
    the actual chat model (BYOK, rate limiting, keyless fallback all live behind it).
    """

    def __init__(self, *, invoke: Callable[[str], Awaitable[str]]) -> None:
        self._invoke = invoke

    async def plan(
        self,
        source: LessonSource,
        *,
        target_seconds: int = target_seconds_for(VideoKind.LESSON),
        simplify: bool = False,
    ) -> SceneContracts:
        prompt = _build_prompt(source, target_seconds, simplify=simplify)
        valid_claim_ids = set(source.packet.claim_ids)
        draft = await invoke_with_parse_repair(
            self._invoke,
            prompt,
            lambda text: _parse_draft(text, valid_claim_ids),
            repair_instruction=_REPAIR_TEMPLATE,
        )
        contract = SceneContracts(
            topic=draft.topic,
            audience=draft.audience,
            visual_archetypes_used=draft.visual_archetypes_used,
            asset_strategy=draft.asset_strategy,
            global_style=video_global_style(),
            scenes=draft.scenes,
        )
        _logger.info(
            "scene_planner.contract_planned",
            scene_count=len(contract.scenes),
            target_seconds=target_seconds,
            archetype_count=len(contract.visual_archetypes_used),
            grounded_claims=len(valid_claim_ids),
        )
        return contract

    async def plan_chaptered(
        self, source: LessonSource, *, target_seconds: int, simplify: bool = False
    ) -> ChapteredSceneContracts:
        """Plan a CHAPTERED contract — the OVERVIEW kind (V5-T1).

        A ~3-minute topic intro exceeds the skill's 3-5-scene envelope, so it is planned as chapters
        of 3-4 scenes that concatenate into one MP4 (plan §0); the chapter count scales with
        ``target_seconds``. Same discipline as the flat ``plan``: the model emits the chapters, the
        system injects ``global_style`` + verifier gates, and a scene citing an unknown claim id
        earns a repair turn — so a longer video never loosens the grounding moat. ``simplify`` (the
        V6 Simpler regenerate) steers toward fewer, plainer scenes.
        """
        prompt = _build_chaptered_prompt(source, target_seconds, simplify=simplify)
        valid_claim_ids = set(source.packet.claim_ids)
        draft = await invoke_with_parse_repair(
            self._invoke,
            prompt,
            lambda text: _parse_chaptered_draft(text, valid_claim_ids),
            repair_instruction=_REPAIR_TEMPLATE,
        )
        contract = ChapteredSceneContracts(
            topic=draft.topic,
            audience=draft.audience,
            visual_archetypes_used=draft.visual_archetypes_used,
            asset_strategy=draft.asset_strategy,
            global_style=video_global_style(),
            chapters=draft.chapters,
        )
        _logger.info(
            "scene_planner.chaptered_contract_planned",
            chapter_count=len(contract.chapters),
            scene_count=len(contract.scenes),
            target_seconds=target_seconds,
            grounded_claims=len(valid_claim_ids),
        )
        return contract


def _suggested_chapters(target_seconds: int) -> int:
    """One chapter per started minute, at least two — so "chaptered" always means >1 chapter, and
    the count rises with length (ceil, not round, so there's no half-minute rounding surprise)."""
    return max(2, math.ceil(target_seconds / _SECONDS_PER_CHAPTER))


def _build_prompt(source: LessonSource, target_seconds: int, *, simplify: bool) -> str:
    return _PROMPT_TEMPLATE.format(
        course_topic=source.course_topic,
        lesson_title=source.lesson_title,
        audience=source.audience,
        prose=source.prose,
        upstream_context=_upstream_block(source.upstream_siblings),
        target_seconds=target_seconds,
        max_objects=MAX_SCENE_OBJECTS,
        grounding_block=_grounding_block(source.packet, _NO_CLAIMS_BLOCK),
        framing_sentinel=FRAMING_ONLY_SENTINEL,
        regenerate_directive=_SIMPLER_DIRECTIVE if simplify else "",
        archetypes=read_skill_asset("references/archetypes.md"),
    )


def _upstream_block(siblings: tuple[SiblingContractDigest, ...]) -> str:
    # The upstream sibling videos this lesson builds on (its prerequisites in the course's video
    # DAG), so the planner reuses their framing instead of re-inventing in a vacuum. Empty (no
    # section at all) for a root lesson, an un-graphed course, or any kind with no upstream.
    if not siblings:
        return ""
    lines = [
        "\nPRIOR VIDEOS IN THIS COURSE (this lesson comes AFTER them — build on what they",
        "established, reuse their terminology, and do NOT re-explain or contradict them):",
    ]
    for sibling in siblings:
        lines.append(f"- {sibling.lesson_title}: {sibling.covers}")
        extras = []
        if sibling.key_terms:
            extras.append("already on screen: " + ", ".join(sibling.key_terms))
        if sibling.archetypes:
            extras.append("visuals: " + ", ".join(sibling.archetypes))
        if extras:
            lines.append("  (" + "; ".join(extras) + ")")
    return "\n".join(lines) + "\n"


def _build_chaptered_prompt(source: LessonSource, target_seconds: int, *, simplify: bool) -> str:
    return _CHAPTERED_PROMPT_TEMPLATE.format(
        course_topic=source.course_topic,
        unit_title=source.lesson_title,
        audience=source.audience,
        prose=source.prose,
        target_seconds=target_seconds,
        chapter_count=_suggested_chapters(target_seconds),
        max_objects=MAX_SCENE_OBJECTS,
        grounding_block=_grounding_block(source.packet, _NO_CLAIMS_BLOCK_CHAPTERED),
        framing_sentinel=FRAMING_ONLY_SENTINEL,
        regenerate_directive=_SIMPLER_DIRECTIVE if simplify else "",
        archetypes=read_skill_asset("references/archetypes.md"),
    )


def _grounding_block(packet: GroundingPacket, no_claims_block: str) -> str:
    # Two structurally different prompt sections — a citable claim list, or a hard "no claims
    # exist, assert nothing" prohibition — feed the template's single {grounding_block} slot, so
    # the branch lives here rather than inline in the template. The no-claims wording differs by
    # kind (lesson vs course-level video), so the caller passes it.
    if packet.is_empty:
        return no_claims_block
    lines = ["- VERIFIED CLAIMS (cite a scene's facts by these ids):"]
    lines += [
        f"  [{claim.id}] {claim.text} (source: {claim.source_label})" for claim in packet.claims
    ]
    return "\n".join(lines)


def _parse_draft(text: str, valid_claim_ids: set[str]) -> ContractDraft:
    draft = ContractDraft.model_validate_json(_json_object(text))
    _validate_scene_sources(draft.scenes, valid_claim_ids)
    _validate_scene_complexity(draft.scenes)
    return draft


def _parse_chaptered_draft(text: str, valid_claim_ids: set[str]) -> ChapteredContractDraft:
    draft = ChapteredContractDraft.model_validate_json(_json_object(text))
    scenes = [scene for chapter in draft.chapters for scene in chapter.scenes]
    _validate_scene_sources(scenes, valid_claim_ids)
    _validate_scene_complexity(scenes)
    return draft


def _json_object(text: str) -> str:
    # The outermost ``{ … }`` span (first brace to last) — captures the object even when the model
    # wraps it in prose; a missing object raises ValueError, which triggers a repair turn.
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("completion contains no JSON object")
    return text[start : end + 1]


def _validate_scene_complexity(scenes: list[SceneContract]) -> None:
    # C1 enforcement: a scene whose ``objects`` list exceeds ``MAX_SCENE_OBJECTS`` renders as a
    # crammed tangle. Raise ValueError (not a quiet pass) precisely so ``invoke_with_parse_repair``
    # feeds the offending scenes + the limit back for a repair turn — the model splits the scene or
    # reveals incrementally rather than the job shipping an over-dense plan. Same self-correction
    # path as ``_validate_scene_sources``; shared by the flat and chaptered parsers.
    over_budget = [scene for scene in scenes if len(scene.objects) > MAX_SCENE_OBJECTS]
    if over_budget:
        detail = ", ".join(f"{scene.id} ({len(scene.objects)} objects)" for scene in over_budget)
        raise ValueError(
            f"these scenes exceed the complexity budget of {MAX_SCENE_OBJECTS} on-screen objects: "
            f"{detail}. Split each into more, simpler scenes, or reveal a bigger structure "
            f"incrementally across beats; cap each scene at {MAX_SCENE_OBJECTS} objects."
        )


def _validate_scene_sources(scenes: list[SceneContract], valid_claim_ids: set[str]) -> None:
    # Unknown-claim-id validation raises ValueError (not a post-parse check in plan()) precisely so
    # invoke_with_parse_repair feeds the offending id back to the model in its repair turn so it can
    # self-correct, rather than the job failing outright. Shared by the flat and chaptered parsers.
    for scene in scenes:
        if scene.sources == [FRAMING_ONLY_SENTINEL]:
            continue
        unknown = [source for source in scene.sources if source not in valid_claim_ids]
        if unknown:
            raise ValueError(
                f"scene {scene.id} cites unknown claim ids {unknown} — cite only the listed "
                f'claim ids or use ["{FRAMING_ONLY_SENTINEL}"]'
            )
