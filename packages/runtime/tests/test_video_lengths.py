"""Per-kind default video lengths (video V5-T1): the target duration PLAN designs each video kind
to, snapshotted onto a job's config at enqueue (V5-T2). Course-level kinds differ — a ~3-minute
OVERVIEW intro vs a ~60-90s SUMMARY trailer / LESSON explainer — so the default is keyed by kind."""

import pytest
from lunaris_runtime.schema import VideoKind
from lunaris_runtime.video_build import target_seconds_for


def test_overview_is_about_three_minutes() -> None:
    # The topic intro is the long-form kind (plan §0: ~3 min, chaptered).
    assert target_seconds_for(VideoKind.OVERVIEW) == 180


@pytest.mark.parametrize("kind", [VideoKind.SUMMARY, VideoKind.LESSON])
def test_summary_and_lesson_are_short_form(kind: VideoKind) -> None:
    # Trailer + lesson explainer both sit in the validated 60-90s envelope (plan §0).
    assert 60 <= target_seconds_for(kind) <= 90


@pytest.mark.parametrize("kind", list(VideoKind))
def test_every_kind_has_a_positive_default(kind: VideoKind) -> None:
    # No kind may fall through to a missing length — PLAN always has a target to design to.
    assert target_seconds_for(kind) > 0
