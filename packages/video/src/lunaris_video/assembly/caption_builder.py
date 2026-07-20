from lunaris_video.assembly.scene_timing import walk_scene_timeline
from lunaris_video.schemas import TimingManifest, VideoContract


def build_webvtt(contract: VideoContract, manifest: TimingManifest) -> str:
    """A WebVTT caption track from the beats (the words) and the manifest (the timing).

    One cue per SPOKEN beat, on the GLOBAL concatenated timeline (``walk_scene_timeline``
    is the single source of truth for where each beat plays — beats accumulate ``anim_s`` and each
    scene's closing fade is folded in, so a cue's clock matches the final MP4 and can never drift
    from the Cinema outline). Silent beats advance the clock but emit no cue; a silent (estimate)
    manifest yields just the ``WEBVTT`` header — captions ship only with narration (plan principle
    8), so the player adds the track only when there is something to show.
    """
    cues: list[str] = []
    for span in walk_scene_timeline(contract.scenes, manifest):
        for beat_span in span.beats:
            if beat_span.spoken:
                text = beat_span.beat.narration.strip()
                cues.append(
                    f"{_timestamp(beat_span.start_s)} --> {_timestamp(beat_span.end_s)}\n{text}"
                )
    if not cues:
        return "WEBVTT\n"
    return "WEBVTT\n\n" + "\n\n".join(cues) + "\n"


def _timestamp(seconds: float) -> str:
    """``HH:MM:SS.mmm`` — the WebVTT cue clock, rounded to whole milliseconds (cue precision)."""
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
