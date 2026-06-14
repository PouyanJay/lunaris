from ..schema import VideoKind

# The target duration (seconds) PLAN designs each video kind to, snapshotted onto a job's config at
# enqueue (V5-T2). Course-level kinds differ in length: the OVERVIEW topic intro is ~3 minutes
# (chaptered — it exceeds the skill's 3-5-scene envelope), while the SUMMARY trailer and LESSON
# explainer sit in the validated 60-90s envelope (plan §0). A future per-user config (V6) overrides
# these per build; until then they are the product defaults.
_DEFAULT_TARGET_SECONDS: dict[VideoKind, int] = {
    VideoKind.LESSON: 75,
    VideoKind.SUMMARY: 75,
    VideoKind.OVERVIEW: 180,
}


def target_seconds_for(kind: VideoKind) -> int:
    """The default target duration (seconds) for a video kind — every kind has one, so PLAN always
    has a length to design to. ``StrEnum`` membership guarantees the lookup never misses."""
    return _DEFAULT_TARGET_SECONDS[kind]
