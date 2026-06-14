"""CourseVideoSourceProvider (video V5-T2): turns a course-level job's grounding snapshot (carried
on ``job.config`` because the course isn't persisted yet — AD-1) into the ``LessonSource`` the
planner plans from, grounding the trailer in the curriculum and the intro in the standard."""

import pytest
from lunaris_runtime.schema import (
    CourseBrief,
    Module,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    VideoJob,
    VideoKind,
)
from lunaris_video.errors import VideoPipelineError
from lunaris_video.grounding import CourseGroundingPacketBuilder
from lunaris_video.models import PacketKind
from lunaris_video.sourcing import CourseVideoSourceProvider


def _provider() -> CourseVideoSourceProvider:
    return CourseVideoSourceProvider(packet_builder=CourseGroundingPacketBuilder())


def _job(kind: VideoKind, grounding: dict[str, object]) -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="user-a",
        course_id="c1",
        lesson_id=None,
        kind=kind,
        input_hash="h",
        config={"grounding": grounding},
    )


async def test_summary_source_grounds_in_the_curriculum_snapshot() -> None:
    # Arrange — the grounding the coordinator stamps for a SUMMARY job.
    modules = [Module(id="m1", title="Sorting"), Module(id="m2", title="Searching")]
    grounding = {"topic": "Algorithms", "modules": [m.model_dump(mode="json") for m in modules]}

    # Act
    source = await _provider().load(_job(VideoKind.SUMMARY, grounding))

    # Assert — a SUMMARY packet built from the snapshot modules; the source frames the trailer.
    assert source.packet.kind is PacketKind.SUMMARY
    assert source.course_topic == "Algorithms"
    assert "Sorting" in source.prose and "Searching" in source.prose
    assert any("2 modules" in claim.text for claim in source.packet.claims)


async def test_overview_source_grounds_in_the_researched_brief_snapshot() -> None:
    # Arrange — the brief snapshot (with researched standard) the coordinator stamps for OVERVIEW.
    brief = CourseBrief(
        subject="English for IELTS",
        goal="reach CLB 10",
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["Write a 250-word essay"],
            sources=[ResearchSource(url="https://x/clb", title="CLB 10")],
        ),
    )
    grounding = {"brief": brief.model_dump(mode="json")}

    # Act
    source = await _provider().load(_job(VideoKind.OVERVIEW, grounding))

    # Assert — an OVERVIEW packet built from the researched standard; the source frames the intro.
    assert source.packet.kind is PacketKind.OVERVIEW
    assert source.course_topic == "English for IELTS"
    assert any("Write a 250-word essay" in claim.text for claim in source.packet.claims)
    assert source.prose  # non-blank framing


async def test_a_job_without_a_grounding_snapshot_fails_clean() -> None:
    # Arrange — a malformed job (no grounding in config); the worker must fail it, not crash.
    job = VideoJob(id="job-1", user_id="u", course_id="c1", kind=VideoKind.SUMMARY, input_hash="h")

    # Act / Assert
    with pytest.raises(VideoPipelineError):
        await _provider().load(job)


async def test_a_lesson_kind_is_rejected_by_the_course_provider() -> None:
    # Arrange / Act / Assert — the course provider serves only the course-level kinds; a LESSON job
    # routes to the lesson provider, never here.
    with pytest.raises(VideoPipelineError):
        await _provider().load(_job(VideoKind.LESSON, {"topic": "x", "modules": []}))
