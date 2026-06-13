from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.models.grounding_packet import GroundingPacket
from lunaris_video.models.lesson_source import LessonSource
from lunaris_video.schemas import FRAMING_ONLY_SENTINEL, ContractDraft, SceneContracts
from lunaris_video.skill import read_skill_asset
from lunaris_video.style import video_global_style

_logger = structlog.get_logger(__name__)

_DEFAULT_TARGET_SECONDS = 75

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

ENVELOPE
- 3 to 5 scenes, each 15-30 seconds; total duration about {target_seconds} seconds.
- Standard arc: problem/hook -> key insight -> mechanism step-by-step -> consequence -> verdict.
- 3-6 beats per scene. Each beat is an object with: id ("b1", "b2", ...), action (what happens
  visually), narration (the exact self-contained clause(s) spoken DURING that action; write for
  the ear, about 2.4 words per second), and min_visual_s (a float floor so fast speech cannot
  rush the visual; REQUIRED when narration is the empty string).
- Scene ids match S<N>_<slug> (e.g. "S1_problem"); slugs are lowercase snake_case.
- Assign each scene exactly one primary archetype from the reference below; compose at most two.
  Never invent a free-form visual when an archetype fits.
- Find the one inspired beat: one scene where the visual's FORM carries the argument. If every
  scene is a generic template fill, revise before answering.

GROUNDING (this pipeline stage has no research access — the verified claims are the ONLY facts you
may assert; a downstream gate diffs every on-screen number and comparison against them)
{grounding_block}
- Per scene, set "sources" to the list of claim ids the scene draws its facts from (e.g.
  ["c1", "c3"]), or to ["{framing_sentinel}"] for a scene that states no empirical facts.
- State a number, ranking or comparison ONLY if it appears verbatim in a claim the scene cites.
  Never invent a figure, and never cite a claim id that is not listed above.

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


class ScenePlanner:
    """The PLAN node: lesson in, validated ``SceneContracts`` out (plan §1.2).

    The model emits a ``ContractDraft`` (everything creative); the system injects what is not
    the model's to decide — ``global_style`` from the enterprise-ui token map and the spec's
    verifier gates. V2 also hands the model the lesson's verifier-PASSED claims and lets it pick
    *which* a scene cites — never invent figures — rejecting any draft that cites a claim id the
    packet does not list. ``invoke`` is the package's only model seam (a plain async text
    completion), so the planner is testable with a scripted stub and the composition root chooses
    the actual chat model (BYOK, rate limiting, keyless fallback all live behind it).
    """

    def __init__(self, *, invoke: Callable[[str], Awaitable[str]]) -> None:
        self._invoke = invoke

    async def plan(
        self, lesson: LessonSource, *, target_seconds: int = _DEFAULT_TARGET_SECONDS
    ) -> SceneContracts:
        prompt = _build_prompt(lesson, target_seconds)
        valid_claim_ids = set(lesson.packet.claim_ids)
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


def _build_prompt(lesson: LessonSource, target_seconds: int) -> str:
    return _PROMPT_TEMPLATE.format(
        course_topic=lesson.course_topic,
        lesson_title=lesson.lesson_title,
        audience=lesson.audience,
        prose=lesson.prose,
        target_seconds=target_seconds,
        grounding_block=_grounding_block(lesson.packet),
        framing_sentinel=FRAMING_ONLY_SENTINEL,
        archetypes=read_skill_asset("references/archetypes.md"),
    )


def _grounding_block(packet: GroundingPacket) -> str:
    # Two structurally different prompt sections — a citable claim list, or a hard "no claims
    # exist, assert nothing" prohibition — feed the template's single {grounding_block} slot, so
    # the branch lives here rather than inline in _PROMPT_TEMPLATE.
    if packet.is_empty:
        return _NO_CLAIMS_BLOCK
    lines = ["- VERIFIED CLAIMS (cite a scene's facts by these ids):"]
    lines += [
        f"  [{claim.id}] {claim.text} (source: {claim.source_label})" for claim in packet.claims
    ]
    return "\n".join(lines)


def _parse_draft(text: str, valid_claim_ids: set[str]) -> ContractDraft:
    # Both failure modes raise ValueError because invoke_with_parse_repair takes ONE parser and
    # treats a ValueError as the repair trigger — so unknown-claim-id validation lives here (not
    # post-parse in plan()) precisely so the model gets the offending id in its repair turn and
    # can self-correct rather than the job failing outright.
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("completion contains no JSON object")
    draft = ContractDraft.model_validate_json(text[start : end + 1])
    for scene in draft.scenes:
        if scene.sources == [FRAMING_ONLY_SENTINEL]:
            continue
        unknown = [source for source in scene.sources if source not in valid_claim_ids]
        if unknown:
            raise ValueError(
                f"scene {scene.id} cites unknown claim ids {unknown} — cite only the listed "
                f'claim ids or use ["{FRAMING_ONLY_SENTINEL}"]'
            )
    return draft
