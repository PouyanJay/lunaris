"""CourseStoreCoverSourceProvider contract (course-cover-images T4): Course → CoverBrief.

The provider distils the owner's course into the art director's brief — topic + a bounded set of
concept-graph labels (topo order, foundational first) + an audience note — and turns a course that
vanished between enqueue and render into a clean ``CoverPipelineError`` rather than a crash.
"""

import pytest
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.sourcing.course_store_cover_source_provider import (
    CourseStoreCoverSourceProvider,
)
from lunaris_runtime.schema import (
    Course,
    CoverJob,
    CoverStylePreset,
    KnowledgeComponent,
    PrerequisiteGraph,
)

_OWNER = "u-1"


class _FakeCourseStore:
    def __init__(self) -> None:
        self._by_owner: dict[tuple[str | None, str], Course] = {}

    def seed(self, course: Course, *, owner_id: str) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._by_owner.get((owner_id, course_id))
        if course is None:
            raise FileNotFoundError(course_id)
        return course

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._by_owner.pop((owner_id, course_id), None) is not None


def _kc(kc_id: str, label: str) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id, label=label, definition="", difficulty=0.5, bloom_ceiling="apply"
    )


def _job() -> CoverJob:
    return CoverJob(
        id="job-1",
        user_id=_OWNER,
        course_id="c-1",
        input_hash="h",
        style_preset=CoverStylePreset.AURORA,
    )


@pytest.mark.asyncio
async def test_brief_carries_topic_audience_preset_and_topo_ordered_labels() -> None:
    graph = PrerequisiteGraph(
        nodes=[_kc("k2", "TLS"), _kc("k1", "TCP")],  # declaration order differs from topo order
        topo_order=["k1", "k2"],
    )
    store = _FakeCourseStore()
    store.seed(
        Course(id="c-1", topic="How HTTPS works", graph=graph, scope_note="engineers"),
        owner_id=_OWNER,
    )

    brief = await CourseStoreCoverSourceProvider(store).load(_job())

    assert brief.topic == "How HTTPS works"
    assert brief.audience == "engineers"
    assert brief.style_preset is CoverStylePreset.AURORA
    assert brief.concept_labels == ("TCP", "TLS")  # topo order, foundational first


@pytest.mark.asyncio
async def test_labels_are_bounded_and_blank_labels_dropped() -> None:
    nodes = [_kc(f"k{i}", f"Concept {i}") for i in range(10)]
    nodes.append(_kc("blank", "   "))
    graph = PrerequisiteGraph(nodes=nodes, topo_order=[n.id for n in nodes])
    store = _FakeCourseStore()
    store.seed(Course(id="c-1", topic="T", graph=graph), owner_id=_OWNER)

    brief = await CourseStoreCoverSourceProvider(store).load(_job())

    assert len(brief.concept_labels) == 6  # capped
    assert all(label.strip() for label in brief.concept_labels)


@pytest.mark.asyncio
async def test_empty_graph_falls_back_to_topic_and_synthesized_audience() -> None:
    store = _FakeCourseStore()
    store.seed(Course(id="c-1", topic="Photosynthesis"), owner_id=_OWNER)

    brief = await CourseStoreCoverSourceProvider(store).load(_job())

    assert brief.concept_labels == ()
    assert brief.audience == "learners studying Photosynthesis"


@pytest.mark.asyncio
async def test_deleted_course_raises_cover_pipeline_error() -> None:
    store = _FakeCourseStore()  # nothing seeded
    with pytest.raises(CoverPipelineError):
        await CourseStoreCoverSourceProvider(store).load(_job())
