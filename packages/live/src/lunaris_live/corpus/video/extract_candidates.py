from .bounded_inventory import bounded_inventory
from .schemas.clip import VideoClip
from .schemas.inventory import VideoGap, VideoInventory
from .schemas.source import VideoSource


def extract_candidates(source: VideoSource) -> VideoInventory:
    """Group whole adjacent cues within chapters; never infer word-level timing."""
    clips: list[VideoClip] = []
    gaps: list[VideoGap] = []
    group: list[int] = []
    group_title = source.title

    def flush() -> None:
        if not group:
            return
        cues = tuple(source.transcript[index] for index in group)
        clips.append(
            VideoClip(
                job_id=source.job_id,
                source_digest=source.source_digest,
                locator=f"video:{source.job_id}:{source.source_digest}:{group[0]}:{group[-1]}",
                start_s=cues[0].start_s,
                end_s=cues[-1].end_s,
                duration_s=source.duration_s,
                title=group_title,
                transcript=cues,
            )
        )
        group.clear()

    chapter_key: int | None = None
    for index, cue in enumerate(source.transcript):
        matches = [
            i
            for i, chapter in enumerate(source.chapters)
            if chapter.start_s <= cue.start_s and cue.end_s <= chapter.end_s
        ]
        key = matches[0] if matches else None
        reason = "cue_too_long" if cue.end_s - cue.start_s > 90 else None
        if source.chapters and key is None:
            reason = "chapter_mismatch"
        if reason:
            flush()
            gaps.append(VideoGap(job_id=source.job_id, reason=reason))
            continue
        if group and (
            len(group) >= 500
            or key != chapter_key
            or cue.end_s - source.transcript[group[0]].start_s > 90
        ):
            flush()
        if not group:
            chapter_key = key
            group_title = source.chapters[key].title if key is not None else source.title
        group.append(index)
    flush()
    if not source.transcript:
        gaps.append(VideoGap(job_id=source.job_id, reason="silent"))
    return bounded_inventory(clips, gaps)
