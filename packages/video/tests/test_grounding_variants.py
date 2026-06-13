"""V2-T4 variant coverage: grounded vs framing-only lessons, and the headline guarantee — a lesson
whose claims were CUT produces a video that asserts NOTHING cut. Drives the REAL grounding chain
end to end (course store → packet builder → planner → Gate C → provenance), with only the
render/QA/assemble leaves stubbed, so the moat is exercised the way a real build would."""

import json
from pathlib import Path

import pytest
from _stubs import StubInvokeModel
from lunaris_runtime.schema import (
    Citation,
    Claim,
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VerifierStatus,
    VideoJob,
    VideoKind,
    VideoProvenance,
)
from lunaris_video.errors import FactualGateError
from lunaris_video.gates import FactualGate, RenderGate, VisualQaGate
from lunaris_video.grounding import LessonGroundingPacketBuilder
from lunaris_video.models import RenderedScene, RenderedVideo, RenderResult
from lunaris_video.pipeline import ContractHashCache, LessonVideoPipeline
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import QaVerdict, SceneContract, VideoContract
from lunaris_video.sourcing import CourseStoreLessonSourceProvider

_OWNER = "00000000-0000-0000-0000-000000000001"
_SCENE_SOURCE = (
    "from manim import *\n"
    "from style_tokens import *\n\n\n"
    "class S1Intro(Scene):\n"
    "    def construct(self):\n"
    "        pass\n"
)


# ── render/QA/assemble leaves (hermetic; no real Manim) ───────────────────────────


class _Renderer:
    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"\x00\x00\x00\x18ftyp" + b"x" * 32)
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


class _Codegen:
    async def generate(self, scene: SceneContract, *, topic: str) -> str:
        return _SCENE_SOURCE

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str:
        return _SCENE_SOURCE

    async def repair_visual(self, scene: SceneContract, *, source: str, defects) -> str:
        return _SCENE_SOURCE


class _Vision:
    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict:
        return QaVerdict(passed=True)


class _Frames:
    async def extract(self, mp4_path: Path) -> list[bytes]:
        return [b"f30", b"f60", b"f90"]


class _Assembler:
    async def assemble(
        self, scenes: list[RenderedScene], contract: VideoContract, *, workdir: Path
    ) -> RenderedVideo:
        return RenderedVideo(
            mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
            poster=b"\xff\xd8\xff" + b"x" * 600,
            contracts_json=contract.model_dump_json().encode(),
            timing_json=b"{}",
        )


class _FakeCourseStore:
    def __init__(self, course: Course) -> None:
        self._course = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        if self._course.id != course_id:
            raise FileNotFoundError(course_id)
        return self._course

    # Protocol surface the pipeline's read path never exercises — present to satisfy ICourseStore.
    def save(self, course: Course, *, owner_id: str | None = None) -> None: ...

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return False


# ── fixtures: courses with controllable claim verdicts ────────────────────────────


def _supported(text: str, citation_id: str) -> Claim:
    return Claim(text=text, supported_by=citation_id, verifier_status=VerifierStatus.SUPPORTED)


def _cut(text: str) -> Claim:
    return Claim(text=text, supported_by=None, verifier_status=VerifierStatus.CUT)


def _course(*claims: Claim) -> Course:
    segments = MerrillSegments(
        activate=Segment(prose="Merge sort is a divide-and-conquer sort.", claims=list(claims)),
        demonstrate=Segment(prose="It splits the array and merges sorted runs."),
        apply=Segment(prose="Trace a small example."),
        integrate=Segment(prose="Where else does divide-and-conquer apply?"),
    )
    lesson = Lesson(id="lesson-1", segments=segments)
    module = Module(id="m1", title="Sorting", competency="sort efficiently", lessons=[lesson])
    return Course(
        id="course-1",
        topic="Algorithms",
        scope_note="for CS undergrads",
        modules=[module],
        provenance=[Citation(id="cite-clrs", title="CLRS")],
    )


def _draft(*, sources: list[str], narration: str) -> str:
    return json.dumps(
        {
            "topic": "Merge sort",
            "audience": "for CS undergrads",
            "visual_archetypes_used": ["process/flow"],
            "asset_strategy": "tier-a procedural",
            "scenes": [
                {
                    "id": "S1_intro",
                    "archetype": "process/flow",
                    "narration": narration,
                    "objects": ["a diagram of the array"],
                    "beats": [{"id": "b1", "action": "the array appears", "narration": narration}],
                    "sources": sources,
                    "duration_s": 12,
                }
            ],
        }
    )


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


def _pipeline(course: Course, draft_json: str, workspace: Path) -> LessonVideoPipeline:
    codegen, renderer = _Codegen(), _Renderer()
    return LessonVideoPipeline(
        lesson_provider=CourseStoreLessonSourceProvider(
            _FakeCourseStore(course), packet_builder=LessonGroundingPacketBuilder()
        ),
        planner=ScenePlanner(invoke=StubInvokeModel([draft_json])),
        factual_gate=FactualGate(),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=_Vision(), codegen=codegen, renderer=renderer, frames=_Frames()
        ),
        assembler=_Assembler(),
        cache=ContractHashCache(),
        workspace_root=workspace,
        model_id="claude-test-model",
    )


# ── the variants ──────────────────────────────────────────────────────────────────


async def test_a_grounded_lesson_lists_its_cited_claims_in_provenance(tmp_path: Path) -> None:
    # Arrange — one verified claim with a figure; the scene cites it and narrates that figure.
    course = _course(_supported("Merge sort sorts 8 elements in 24 comparisons.", "cite-clrs"))
    draft = _draft(sources=["c1"], narration="Watch it sort 8 elements in 24 comparisons.")

    # Act
    video = await _pipeline(course, draft, tmp_path).produce(_job())

    # Assert — the video shipped, and its provenance names the claim it grounds on.
    provenance = VideoProvenance.model_validate_json(video.provenance_json)
    assert provenance.claim_ids == ["c1"]


async def test_a_framing_only_lesson_produces_a_video_that_asserts_nothing(tmp_path: Path) -> None:
    # Arrange — no verified claims: every scene must be framing only, asserting no figures.
    course = _course()  # prose only, no claims
    draft = _draft(
        sources=["framing only - no empirical claims"],
        narration="Sorting is everywhere, and it makes data searchable.",
    )

    # Act
    video = await _pipeline(course, draft, tmp_path).produce(_job())

    # Assert — a real video, but provenance asserts nothing (no claim ids).
    provenance = VideoProvenance.model_validate_json(video.provenance_json)
    assert provenance.claim_ids == []


async def test_a_lesson_whose_claim_was_cut_cannot_assert_the_cut_figure(tmp_path: Path) -> None:
    # Arrange — the figure "1000" lives ONLY in a CUT claim, so it never reaches the packet. A
    # framing-only scene that smuggles it in is exactly the "video asserts what the text couldn't
    # prove" failure V2 exists to stop.
    course = _course(_cut("Merge sort is 1000x faster than every other sort."))
    draft = _draft(
        sources=["framing only - no empirical claims"],
        narration="Merge sort is 1000x faster than every other sort.",
    )

    # Act / Assert — Gate C fails the job: the cut figure has no grounding.
    with pytest.raises(FactualGateError) as caught:
        await _pipeline(course, draft, tmp_path).produce(_job())
    assert "1000" in caught.value.unsupported


async def test_a_mixed_lesson_keeps_the_supported_claim_and_drops_the_cut_one(
    tmp_path: Path,
) -> None:
    # Arrange — one SUPPORTED claim (figure 8) survives into the packet as c1; one CUT claim
    # (figure 1000) is dropped. A scene grounds on c1 and narrates BOTH figures: the supported 8 is
    # fine, the cut 1000 is not — proving the builder filters per-claim, not per-lesson.
    course = _course(
        _supported("Merge sort sorts 8 elements.", "cite-clrs"),
        _cut("Merge sort is 1000x faster than every other sort."),
    )
    draft = _draft(sources=["c1"], narration="It sorts 8 elements and is 1000x faster.")

    # Act / Assert — only the cut figure is unsupported; the supported one passed.
    with pytest.raises(FactualGateError) as caught:
        await _pipeline(course, draft, tmp_path).produce(_job())
    assert caught.value.unsupported == ["1000"]


async def test_a_mixed_lesson_ships_when_it_asserts_only_the_supported_figure(
    tmp_path: Path,
) -> None:
    # Arrange — same mixed lesson, but the scene narrates ONLY the supported figure.
    course = _course(
        _supported("Merge sort sorts 8 elements.", "cite-clrs"),
        _cut("Merge sort is 1000x faster than every other sort."),
    )
    draft = _draft(sources=["c1"], narration="Watch it sort 8 elements.")

    # Act
    video = await _pipeline(course, draft, tmp_path).produce(_job())

    # Assert — the video ships grounded on the surviving claim; the cut claim is nowhere in sight.
    provenance = VideoProvenance.model_validate_json(video.provenance_json)
    assert provenance.claim_ids == ["c1"]


async def test_a_cut_claim_lesson_can_still_ship_a_clean_framing_only_video(tmp_path: Path) -> None:
    # Arrange — same cut claim, but the planner behaves: it asserts nothing the verifier dropped.
    course = _course(_cut("Merge sort is 1000x faster than every other sort."))
    draft = _draft(
        sources=["framing only - no empirical claims"],
        narration="Merge sort splits the work and combines the results.",
    )

    # Act
    video = await _pipeline(course, draft, tmp_path).produce(_job())

    # Assert — a video ships, grounded in nothing (the cut claim never appears in provenance).
    provenance = VideoProvenance.model_validate_json(video.provenance_json)
    assert provenance.claim_ids == []


async def test_a_scene_citing_a_cut_claims_id_is_rejected_at_planning(tmp_path: Path) -> None:
    # Arrange — a cut claim has no id in the packet, so a scene that tries to cite "c1" is an
    # invented citation; the planner exhausts its repair budget (the stub repeats the bad draft).
    course = _course(_cut("Merge sort is 1000x faster than every other sort."))
    draft = _draft(sources=["c1"], narration="Merge sort splits the work.")

    # Act / Assert — the build fails cleanly rather than grounding on a dropped claim.
    with pytest.raises(ValueError, match="unknown claim ids"):
        await _pipeline(course, draft, tmp_path).produce(_job())
