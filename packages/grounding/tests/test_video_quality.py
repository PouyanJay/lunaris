"""CQ Phase 2 T4 — the deterministic video metric scorer (guards → authority → engagement-sanity).

The relevance judge scores CONTENT; this scores the METRICS, separately and label-blind. Metrics
catch "bad" (drop the unplayable, penalize the thin/over-long), they never certify "great".
"""

from lunaris_grounding import VideoResult, passes_video_guards, video_quality_score


def _video(**overrides: object) -> VideoResult:
    return VideoResult(url="https://youtu.be/x", title="t", **overrides)  # type: ignore[arg-type]


def test_non_embeddable_video_fails_the_hard_guard() -> None:
    assert passes_video_guards(_video(embeddable=True)) is True
    assert passes_video_guards(_video(embeddable=False)) is False


def test_unenriched_video_has_no_metric_score() -> None:
    # No duration / captions / counts / authority → nothing to weigh → None (judge stands alone).
    assert video_quality_score(_video()) is None


def test_a_healthy_video_outscores_a_thin_clickbait() -> None:
    # Arrange — a captioned, lesson-length video vs a sub-3-minute one.
    healthy = _video(duration_seconds=720, has_captions=True)
    thin = _video(duration_seconds=45)

    # Act
    healthy_score = video_quality_score(healthy)
    thin_score = video_quality_score(thin)

    # Assert — both are scored (they carry signal), and quality separates them.
    assert healthy_score is not None and thin_score is not None
    assert healthy_score > thin_score


def test_an_allowlisted_channel_boosts_authority() -> None:
    # Arrange — same video, scored without then with its channel on the authority allowlist.
    video = _video(duration_seconds=720, channel_id="UC_official")

    # Act / Assert — the allowlist lifts the score (authority weight).
    base = video_quality_score(video)
    boosted = video_quality_score(video, authority_channels=frozenset({"UC_official"}))
    assert base is not None and boosted is not None
    assert boosted > base


def test_a_very_long_video_is_penalized_not_dropped() -> None:
    # A 2-hour video still scores (it could be input material) but below the healthy band.
    long_score = video_quality_score(_video(duration_seconds=7200))
    healthy_score = video_quality_score(_video(duration_seconds=720))
    assert long_score is not None and healthy_score is not None
    assert long_score < healthy_score
    assert passes_video_guards(_video(duration_seconds=7200)) is True  # not a hard drop
