"""Only aligned finite source cues produce bounded, stable clip candidates."""

import pytest
from lunaris_live.corpus.video.extract_candidates import extract_candidates
from lunaris_live.corpus.video.schemas.cue import Cue
from lunaris_live.corpus.video.schemas.source import VideoSource
from pydantic import ValidationError


def source(**changes: object) -> VideoSource:
    return VideoSource.model_validate(
        {
            "job_id": "job1",
            "source_digest": "a" * 64,
            "title": "Records",
            "duration_s": 110,
            "chapters": [{"title": "Basics", "start_s": 0, "end_s": 110}],
            "transcript": [
                {"start_s": 0, "end_s": 40, "text": "A record."},
                {"start_s": 40, "end_s": 80, "text": "Its fields."},
                {"start_s": 80, "end_s": 110, "text": "Its uses."},
            ],
            **changes,
        }
    )


def test_candidates_group_whole_cues_and_never_exceed_90_seconds() -> None:
    result = extract_candidates(source())
    assert [(c.start_s, c.end_s) for c in result.clips] == [(0, 80), (80, 110)]
    assert result.clips[0].transcript[1].text == "Its fields."
    assert result.clips[0].source_digest == "a" * 64
    assert extract_candidates(source()) == result
    assert result.gaps == ()
    assert all(":" in c.locator and "/" not in c.locator for c in result.clips)


def test_chapter_boundaries_prevent_unrelated_cue_grouping() -> None:
    result = extract_candidates(
        source(
            chapters=[
                {"title": "Basics", "start_s": 0, "end_s": 40},
                {"title": "Use", "start_s": 40, "end_s": 110},
            ]
        )
    )
    assert [(c.title, c.start_s, c.end_s) for c in result.clips] == [
        ("Basics", 0, 40),
        ("Use", 40, 110),
    ]


def test_long_cue_is_a_gap_not_invented_word_timestamps() -> None:
    result = extract_candidates(source(transcript=[{"start_s": 0, "end_s": 100, "text": "Long"}]))
    assert result.clips == ()
    assert result.gaps[0].reason == "cue_too_long"


@pytest.mark.parametrize("start,end", [(float("nan"), 2), (0, float("inf")), (-1, 1), (2, 1)])
def test_invalid_cue_timings_fail_at_boundary(start: float, end: float) -> None:
    with pytest.raises(ValidationError):
        Cue(start_s=start, end_s=end, text="Words")


@pytest.mark.parametrize(
    "cues",
    [
        [{"start_s": 100, "end_s": 111, "text": "Past duration"}],
        [
            {"start_s": 5, "end_s": 10, "text": "First"},
            {"start_s": 8, "end_s": 12, "text": "Overlap"},
        ],
    ],
)
def test_out_of_bounds_and_overlapping_timeline_is_rejected(
    cues: list[dict[str, str | float]],
) -> None:
    with pytest.raises(ValidationError):
        source(transcript=cues)


def test_silent_source_exposes_gap() -> None:
    result = extract_candidates(source(transcript=[]))
    assert result.clips == ()
    assert result.gaps[0].reason == "silent"


def test_many_rejected_cues_keep_bounded_gap_report() -> None:
    value = source(
        duration_s=4000,
        chapters=[{"title": "Other", "start_s": 3000, "end_s": 4000}],
        transcript=[{"start_s": i, "end_s": i + 0.5, "text": "Unmatched"} for i in range(1200)],
    )
    result = extract_candidates(value)
    assert len(result.gaps) == 1000
    assert result.gaps[-1].reason == "inventory_limit"


def test_aggregate_candidate_report_caps_clips_and_preserves_limit_signal() -> None:
    from lunaris_live.corpus.video.bounded_inventory import bounded_inventory
    from lunaris_live.corpus.video.schemas.inventory import VideoGap

    clip = extract_candidates(source()).clips[0]
    result = bounded_inventory([clip] * 6000, [VideoGap(reason="stale")] * 1200)
    assert len(result.clips) == 5000
    assert len(result.gaps) == 1000
    assert result.gaps[-1].reason == "inventory_limit"
