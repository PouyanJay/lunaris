from .video_result import VideoResult

# Duration band (seconds) a real lesson video tends to fall in: under ~3 min is usually thin or
# clickbait, over ~60 min is rarely a single lesson unit. Outside the band is a soft penalty, not a
# drop — a long lecture can still be good input material — so the content judge still weighs it.
_MIN_HEALTHY_SECONDS = 180
_MAX_HEALTHY_SECONDS = 3600
# A plausible like/view ratio. Used only as a weak sanity nudge (never the ranker) — absolute view
# counts are the popularity bias the plan warns against, so they never score.
_MIN_HEALTHY_RATIO = 0.005
_MAX_HEALTHY_RATIO = 0.25
# The neutral start + each bounded nudge (the scorer's tunable weights, named so they're calibrated
# in one place). Metrics catch "bad", they never certify "great", so the deltas stay small.
_BASE_SCORE = 0.5
_HEALTHY_DURATION_BONUS = 0.15
_SHORT_DURATION_PENALTY = 0.2  # too short — usually thin or clickbait
_LONG_DURATION_PENALTY = 0.1  # very long — rarely a single lesson unit
_CAPTIONS_BONUS = 0.1  # accessibility + the content is readable
_AUTHORITY_BONUS = 0.2  # an official / vetted channel
_ENGAGEMENT_BONUS = 0.05  # a plausible like/view ratio


def passes_video_guards(video: VideoResult) -> bool:
    """The hard gate (CQ Phase 2 T4): drop a video we can't actually play.

    Only the unambiguous, drop-worthy signal we have lives here — ``embeddable`` (a non-embeddable
    video can't show in the reader's facade). Soft quality signals (duration, captions, authority,
    engagement) are weights in ``video_quality_score``, not drops, so recall isn't thrown away.
    """
    return video.embeddable


def video_quality_score(
    video: VideoResult, *, authority_channels: frozenset[str] = frozenset()
) -> float | None:
    """A deterministic 0..1 quality weight for a video, from its metric signals (CQ Phase 2 T4).

    Mirrors the grounding credibility scorer: a deterministic signal the curator blends into a kept
    resource's credibility, computed separately from (and invisible to) the relevance judge — the
    judge scores CONTENT, this scores the metrics. Metrics catch "bad"; they never certify "great".
    Each signal is a bounded nudge around a neutral base.

    Returns ``None`` when the video carries NO metric signal at all (an unenriched result — no key,
    or ``videos.list`` failed): with nothing to weigh, the judge's content credibility stands alone
    rather than being dragged toward a fabricated neutral. ``authority_channels`` is per-domain data
    (curated channel ids); empty by default, so no authority is invented where none is known.
    """
    has_authority = bool(video.channel_id and video.channel_id in authority_channels)
    if _has_no_metric_signal(video, has_authority=has_authority):
        return None
    score = (
        _BASE_SCORE
        + _duration_nudge(video)
        + (_CAPTIONS_BONUS if video.has_captions else 0.0)
        + (_AUTHORITY_BONUS if has_authority else 0.0)
        + _engagement_nudge(video)
    )
    return max(0.0, min(1.0, score))


def _has_no_metric_signal(video: VideoResult, *, has_authority: bool) -> bool:
    """True when nothing about the video can contribute a score (an unenriched result)."""
    return (
        video.duration_seconds is None
        and not video.has_captions
        and video.view_count is None
        and not has_authority
    )


def _duration_nudge(video: VideoResult) -> float:
    """Bonus inside the healthy lesson-length band, a soft penalty outside it; 0 when unknown."""
    if video.duration_seconds is None:
        return 0.0
    if _MIN_HEALTHY_SECONDS <= video.duration_seconds <= _MAX_HEALTHY_SECONDS:
        return _HEALTHY_DURATION_BONUS
    if video.duration_seconds < _MIN_HEALTHY_SECONDS:
        return -_SHORT_DURATION_PENALTY
    return -_LONG_DURATION_PENALTY


def _engagement_nudge(video: VideoResult) -> float:
    """A weak sanity nudge for a plausible like/view ratio; 0 otherwise (never a penalty)."""
    if video.view_count and video.like_count is not None and video.view_count > 0:
        ratio = video.like_count / video.view_count
        if _MIN_HEALTHY_RATIO <= ratio <= _MAX_HEALTHY_RATIO:
            return _ENGAGEMENT_BONUS
    return 0.0
