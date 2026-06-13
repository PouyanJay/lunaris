from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.models.lesson_source import LessonSource
from lunaris_video.schemas import ContractDraft, SceneContracts
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
- Lesson text (the ONLY source of facts), between the markers:
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

GROUNDING (this pipeline stage has no research access)
- Narration and on-screen text may state ONLY facts present in the lesson text above. Never
  introduce numbers, rankings or comparisons that the lesson does not contain.
- Per scene, set "sources" to ["lesson: {lesson_title}"] when the scene states lesson facts, or
  to ["framing only - no empirical claims"] when it makes no empirical claims.

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


class ScenePlanner:
    """The PLAN node: lesson in, validated ``SceneContracts`` out (plan §1.2).

    The model emits a ``ContractDraft`` (everything creative); the system injects what is not
    the model's to decide — ``global_style`` from the enterprise-ui token map and the spec's
    verifier gates. ``invoke`` is the package's only model seam (a plain async text completion),
    so the planner is testable with a scripted stub and the composition root chooses the actual
    chat model (BYOK, rate limiting, keyless fallback all live behind it).
    """

    def __init__(self, *, invoke: Callable[[str], Awaitable[str]]) -> None:
        self._invoke = invoke

    async def plan(
        self, lesson: LessonSource, *, target_seconds: int = _DEFAULT_TARGET_SECONDS
    ) -> SceneContracts:
        prompt = _build_prompt(lesson, target_seconds)
        draft = await invoke_with_parse_repair(
            self._invoke,
            prompt,
            _parse_draft,
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
        )
        return contract


def _build_prompt(lesson: LessonSource, target_seconds: int) -> str:
    return _PROMPT_TEMPLATE.format(
        course_topic=lesson.course_topic,
        lesson_title=lesson.lesson_title,
        audience=lesson.audience,
        prose=lesson.prose,
        target_seconds=target_seconds,
        archetypes=read_skill_asset("references/archetypes.md"),
    )


def _parse_draft(text: str) -> ContractDraft:
    """Strict draft parse; raises ``ValueError`` (the repair trigger) on anything malformed."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("completion contains no JSON object")
    return ContractDraft.model_validate_json(text[start : end + 1])
