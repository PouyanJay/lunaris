"""V6-T4 variant coverage: the per-user video config gates + stamps every video kind end-to-end.

The build coordinator stamps each enqueued job with the tenant's chosen length (per kind) and voice
toggle; the master toggle being off is the composition root's job (proven in the build-gate test).
Here we parametrise the stamping over all three kinds x the voice toggle, so a length or voice
regression on any kind is caught."""

import pytest
from lunaris_runtime.persistence import InMemoryVideoJobQueue, InMemoryVideoStorage
from lunaris_runtime.schema import (
    CourseBrief,
    Module,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    VideoKind,
)
from lunaris_runtime.video_build import QueueVideoBuildCoordinator, VideoConfig

_OWNER = "user-a"


def _video_config(*, voice: bool) -> VideoConfig:
    # Distinct length per kind, none equal to another, so a mis-keyed lookup can't pass by accident.
    return VideoConfig(
        enabled=True, voice=voice, summary_seconds=60, overview_seconds=200, lesson_seconds=80
    )


def _brief() -> CourseBrief:
    return CourseBrief(
        subject="Algorithms",
        goal="reason about cost",
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["analyse Big-O"],
            sources=[ResearchSource(url="https://x/clrs", title="CLRS")],
        ),
    )


async def _enqueue(coordinator: QueueVideoBuildCoordinator, kind: VideoKind) -> str | None:
    match kind:
        case VideoKind.LESSON:
            return await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")
        case VideoKind.SUMMARY:
            return await coordinator.enqueue_summary(
                course_id="c1", topic="Algorithms", modules=[Module(id="m1", title="Sorting")]
            )
        case VideoKind.OVERVIEW:
            return await coordinator.enqueue_overview(course_id="c1", brief=_brief())
        case _:
            raise ValueError(f"unhandled VideoKind: {kind}")


@pytest.mark.parametrize("voice", [True, False])
@pytest.mark.parametrize("kind", list(VideoKind))
async def test_coordinator_stamps_each_kinds_length_and_voice(kind: VideoKind, voice: bool) -> None:
    # Arrange — a tenant config with a distinct length per kind and a voice toggle.
    queue = InMemoryVideoJobQueue()
    config = _video_config(voice=voice)
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER, video_config=config
    )

    # Act
    job_id = await _enqueue(coordinator, kind)

    # Assert — the job carries THIS kind's length and the voice toggle, end-to-end.
    assert job_id is not None
    job = await queue.get(job_id=job_id, owner_id=_OWNER)
    assert job is not None
    assert job.kind is kind
    assert job.config["target_seconds"] == config.target_seconds(kind)
    assert job.config["voice"] is voice
