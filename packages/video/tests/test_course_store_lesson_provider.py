"""CourseStoreLessonSourceProvider tests: a job resolves to its lesson's prose (the four Merrill
segments concatenated), with clean domain failures when the course or lesson is missing."""

from collections.abc import Callable

import pytest
from lunaris_runtime.persistence import PersistenceError
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    Claim,
    Course,
    Edge,
    KnowledgeComponent,
    Lesson,
    MerrillSegments,
    Module,
    PrerequisiteGraph,
    Segment,
    VerifierStatus,
    VideoArtifact,
    VideoJob,
    VideoJobStatus,
    VideoKind,
)
from lunaris_video.errors import VideoPipelineError
from lunaris_video.grounding import CourseGroundingPacketBuilder
from lunaris_video.models import PacketKind
from lunaris_video.schemas import SceneContracts
from lunaris_video.sourcing import CourseStoreLessonSourceProvider

_OWNER = "00000000-0000-0000-0000-000000000001"


class _FakeVideoStorage:
    """Just enough IVideoStorage for upstream-contract fetch: a path→bytes map; a miss raises."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    async def download(self, *, path: str) -> bytes:
        try:
            return self._files[path]
        except KeyError as exc:
            raise PersistenceError(f"no object at {path}") from exc

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None: ...


def _kc(kc_id: str) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition=f"the {kc_id}",
        difficulty=0.5,
        bloom_ceiling=BloomLevel.UNDERSTAND,
    )


def _two_lesson_course(*, l1_video: VideoArtifact | None) -> Course:
    """M1 teaches k1 (lesson l1, optionally with a built video); M2 teaches k2 (lesson l2);
    k1 -> k2, so l2's video depends on l1's."""
    graph = PrerequisiteGraph(
        nodes=[_kc("k1"), _kc("k2")],
        edges=[Edge(from_="k1", to="k2", strength=1.0)],
        topo_order=["k1", "k2"],
        is_acyclic=True,
    )
    m1 = Module(
        id="m1",
        title="Neurons",
        competency="what a neuron is",
        kcs=["k1"],
        lessons=[Lesson(id="l1", segments=_segments(), video=l1_video)],
    )
    m2 = Module(
        id="m2",
        title="Learning",
        competency="how a network learns",
        kcs=["k2"],
        lessons=[Lesson(id="l2", segments=_segments())],
    )
    return Course(
        id="course-1",
        topic="Neural networks",
        scope_note="for newcomers",
        modules=[m1, m2],
        graph=graph,
    )


def _l2_job() -> VideoJob:
    return VideoJob(
        id="job-l2",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="l2",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


def _upstream_contract_path() -> str:
    return f"{_OWNER}/course-1/job-l1/scene_contracts.json"


def _provider_with_storage(
    course: Course, storage: _FakeVideoStorage
) -> CourseStoreLessonSourceProvider:
    return CourseStoreLessonSourceProvider(
        _FakeCourseStore(course),
        packet_builder=CourseGroundingPacketBuilder(),
        video_storage=storage,
    )


def _provider(course: Course | None) -> CourseStoreLessonSourceProvider:
    return CourseStoreLessonSourceProvider(
        _FakeCourseStore(course), packet_builder=CourseGroundingPacketBuilder()
    )


class _FakeCourseStore:
    def __init__(self, course: Course | None) -> None:
        self._course = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        if self._course is None or self._course.id != course_id:
            raise FileNotFoundError(course_id)
        return self._course

    def save(self, course: Course, *, owner_id: str | None = None) -> None: ...

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return False


def _segments() -> MerrillSegments:
    return MerrillSegments(
        activate=Segment(prose="Recall that arrays hold ordered elements."),
        demonstrate=Segment(prose="Merge sort splits the array in half."),
        apply=Segment(prose="Trace the merge of [3,1] and [2,4]."),
        integrate=Segment(prose="Where else does divide-and-conquer apply?"),
    )


def _course(*, lesson_id: str = "lesson-1") -> Course:
    lesson = Lesson(id=lesson_id, segments=_segments())
    module = Module(
        id="m1", title="Sorting", competency="sort an array efficiently", lessons=[lesson]
    )
    return Course(
        id="course-1", topic="Algorithms", scope_note="for CS undergrads", modules=[module]
    )


def _grounded_course() -> Course:
    segments = MerrillSegments(
        activate=Segment(
            prose="Merge sort is a divide-and-conquer sort.",
            claims=[
                Claim(
                    text="Merge sort runs in O(n log n) time.",
                    supported_by="cite-clrs",
                    verifier_status=VerifierStatus.SUPPORTED,
                )
            ],
        ),
        demonstrate=Segment(prose="It splits the array in half repeatedly."),
        apply=Segment(prose="Trace the merge."),
        integrate=Segment(prose="Where else does it help?"),
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


def _job(*, lesson_id: str | None = "lesson-1") -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id=lesson_id,
        kind=VideoKind.LESSON,
        input_hash="h",
    )


async def test_load_flattens_the_lesson_into_a_source() -> None:
    # Arrange
    provider = _provider(_course())

    # Act
    source = await provider.load(_job())

    # Assert — course topic, module competency as the lesson title, scope as audience, and ALL
    # four segment proses in order.
    assert source.course_topic == "Algorithms"
    assert source.lesson_title == "sort an array efficiently"
    assert source.audience == "for CS undergrads"
    assert "arrays hold ordered elements" in source.prose
    assert "divide-and-conquer" in source.prose


async def test_load_composes_the_grounding_packet_onto_the_source() -> None:
    # Arrange — the lesson carries one SUPPORTED claim grounded by a course citation.
    provider = _provider(_grounded_course())

    # Act
    source = await provider.load(_job())

    # Assert — the GROUND stage hands PLAN a packet, not just prose (cross-cutting principle 2).
    assert source.packet.kind is PacketKind.LESSON
    assert [claim.text for claim in source.packet.claims] == ["Merge sort runs in O(n log n) time."]
    assert source.packet.claims[0].id == "c1"
    assert source.packet.claims[0].source_label == "CLRS"


async def test_a_lesson_with_no_supported_claims_loads_an_empty_packet() -> None:
    # Arrange — prose exists (so the load succeeds) but nothing was verified: framing-only.
    provider = _provider(_course())

    # Act
    source = await provider.load(_job())

    # Assert — a valid load with an empty packet; PLAN must make every scene framing-only.
    assert source.packet.is_empty


async def test_missing_course_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = _provider(None)

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found"):
        await provider.load(_job())


async def test_missing_lesson_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = _provider(_course(lesson_id="other"))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found in course"):
        await provider.load(_job(lesson_id="lesson-1"))


async def test_a_lesson_job_without_a_lesson_id_is_rejected() -> None:
    # Arrange
    provider = _provider(_course())

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="no lesson_id"):
        await provider.load(_job(lesson_id=None))


async def test_a_lesson_with_only_blank_prose_is_rejected() -> None:
    # Arrange — a lesson whose four segments are all empty: nothing to ground a video on.
    blank = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    lesson = Lesson(id="lesson-1", segments=blank)
    module = Module(id="m1", title="Sorting", lessons=[lesson])
    course = Course(id="course-1", topic="Algorithms", modules=[module])
    provider = _provider(course)

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="no prose"):
        await provider.load(_job())


# ── T3: upstream-sibling context ──────────────────────────────────────────────


async def test_load_attaches_the_upstream_sibling_digest(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — l2 depends on l1 (k2 requires k1); l1 has a READY video, its contract in storage.
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    upstream_contract = make_lesson_contract(topic="What a neuron is")
    storage = _FakeVideoStorage(
        {_upstream_contract_path(): upstream_contract.model_dump_json().encode()}
    )
    provider = _provider_with_storage(course, storage)

    # Act
    source = await provider.load(_l2_job())

    # Assert — l2's source carries l1's digest (module competency as the title, topic as covers).
    assert len(source.upstream_siblings) == 1
    digest = source.upstream_siblings[0]
    assert digest.lesson_title == "what a neuron is"
    assert digest.covers == "What a neuron is"


async def test_no_storage_means_no_upstream_context() -> None:
    # Arrange — a provider built without a video store (the back-compat / no-fetch path).
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    provider = CourseStoreLessonSourceProvider(
        _FakeCourseStore(course), packet_builder=CourseGroundingPacketBuilder()
    )

    # Act
    source = await provider.load(_l2_job())

    # Assert
    assert source.upstream_siblings == ()


async def test_an_unbuilt_upstream_is_skipped() -> None:
    # Arrange — l1 has no video yet (it has not been built), so there is nothing to digest.
    course = _two_lesson_course(l1_video=None)
    provider = _provider_with_storage(course, _FakeVideoStorage({}))

    # Act
    source = await provider.load(_l2_job())

    # Assert — best-effort: no upstream digest, and the load still succeeds.
    assert source.upstream_siblings == ()


async def test_a_missing_upstream_contract_is_skipped() -> None:
    # Arrange — l1's video is READY but its contract is absent from storage (best-effort skip).
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    provider = _provider_with_storage(course, _FakeVideoStorage({}))  # nothing stored

    # Act
    source = await provider.load(_l2_job())

    # Assert
    assert source.upstream_siblings == ()


async def test_an_unparseable_upstream_contract_is_skipped() -> None:
    # Arrange — l1's video is READY and its contract is in storage, but the bytes are garbage
    # (schema drift / partial write). The digest is skipped, the load still succeeds.
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    storage = _FakeVideoStorage({_upstream_contract_path(): b"not a scene contract at all"})
    provider = _provider_with_storage(course, storage)

    # Act
    source = await provider.load(_l2_job())

    # Assert
    assert source.upstream_siblings == ()


async def test_a_root_lesson_has_no_upstream(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — l1 is the root (k1 has no prerequisite); regenerating IT should pull no upstream.
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    storage = _FakeVideoStorage(
        {_upstream_contract_path(): make_lesson_contract().model_dump_json().encode()}
    )
    provider = _provider_with_storage(course, storage)
    l1_job = VideoJob(
        id="job-l1",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="l1",
        kind=VideoKind.LESSON,
        input_hash="h",
    )

    # Act
    source = await provider.load(l1_job)

    # Assert
    assert source.upstream_siblings == ()


async def test_a_reuse_mode_regenerate_skips_the_upstream_fetch(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — a RETRY / ADD_NARRATION regenerate reuses the prior contract and never re-plans, so
    # it needs no upstream context. Even with a store and a built upstream, the fetch is skipped.
    course = _two_lesson_course(
        l1_video=VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id="job-l1")
    )
    storage = _FakeVideoStorage(
        {_upstream_contract_path(): make_lesson_contract().model_dump_json().encode()}
    )
    provider = _provider_with_storage(course, storage)
    retry_job = VideoJob(
        id="job-l2",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="l2",
        kind=VideoKind.LESSON,
        input_hash="h",
        config={"regenerate": {"mode": "retry", "contract_path": "prior/path"}},
    )

    # Act
    source = await provider.load(retry_job)

    # Assert
    assert source.upstream_siblings == ()


async def test_all_upstream_lessons_are_digested_in_topological_order(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — a 3-lesson chain k1 -> k2 -> k3; l3 depends on BOTH l1 and l2, both built. The two
    # digests must arrive in topological order (l1 before l2).
    graph = PrerequisiteGraph(
        nodes=[_kc("k1"), _kc("k2"), _kc("k3")],
        edges=[Edge(from_="k1", to="k2", strength=1.0), Edge(from_="k2", to="k3", strength=1.0)],
        topo_order=["k1", "k2", "k3"],
        is_acyclic=True,
    )

    def _ready(job_id: str) -> VideoArtifact:
        return VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.READY, job_id=job_id)

    course = Course(
        id="course-1",
        topic="Neural networks",
        scope_note="for newcomers",
        modules=[
            Module(
                id="m1",
                title="A",
                competency="neurons",
                kcs=["k1"],
                lessons=[Lesson(id="l1", segments=_segments(), video=_ready("job-l1"))],
            ),
            Module(
                id="m2",
                title="B",
                competency="layers",
                kcs=["k2"],
                lessons=[Lesson(id="l2", segments=_segments(), video=_ready("job-l2"))],
            ),
            Module(
                id="m3",
                title="C",
                competency="learning",
                kcs=["k3"],
                lessons=[Lesson(id="l3", segments=_segments())],
            ),
        ],
        graph=graph,
    )
    storage = _FakeVideoStorage(
        {
            f"{_OWNER}/course-1/job-l1/scene_contracts.json": make_lesson_contract(topic="Neurons")
            .model_dump_json()
            .encode(),
            f"{_OWNER}/course-1/job-l2/scene_contracts.json": make_lesson_contract(topic="Layers")
            .model_dump_json()
            .encode(),
        }
    )
    provider = _provider_with_storage(course, storage)
    l3_job = VideoJob(
        id="job-l3",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="l3",
        kind=VideoKind.LESSON,
        input_hash="h",
    )

    # Act
    source = await provider.load(l3_job)

    # Assert — both upstream digests, l1 (topo-earlier) before l2.
    assert [d.covers for d in source.upstream_siblings] == ["Neurons", "Layers"]
