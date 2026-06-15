from lunaris_video.assembly.scene_timing import SCENE_CLOSE_FADE_S
from lunaris_video.schemas import TimingManifest, VideoContract


def build_webvtt(contract: VideoContract, manifest: TimingManifest) -> str:
    """A WebVTT caption track from the beats (the words) and the manifest (the timing).

    One cue per SPOKEN beat, on the GLOBAL timeline of the concatenated video — the cursor
    accumulates ``anim_s`` across every scene's beats in order, PLUS ``SCENE_CLOSE_FADE_S`` after
    each scene (the closing fade the render plays after a scene's beats), so a cue's clock matches
    where its beat actually plays in the final MP4. Without that per-scene gap the cues drift ahead
    of the video by the fade duration at every scene boundary, compounding across scenes. Silent
    beats (empty narration) advance the cursor but emit no cue. A silent (estimate) manifest yields
    just the ``WEBVTT`` header — captions ship only with narration (plan principle 8), so the player
    adds the track only when there is something to show.
    """
    cues: list[str] = []
    cursor = 0.0
    for scene in contract.scenes:
        timing_by_beat = {beat.id: beat for beat in manifest[scene.id].beats}
        for beat in scene.beats:
            timing = timing_by_beat[beat.id]
            start, end = cursor, cursor + timing.anim_s
            cursor = end
            # A cue rides a synthesized clip — `audio` is set only for a spoken, voiced beat. A
            # silent beat (and every beat of a silent/estimate manifest) advances the clock but
            # captions nothing, so an estimate video yields just the header.
            if timing.audio and beat.narration.strip():
                cues.append(f"{_timestamp(start)} --> {_timestamp(end)}\n{beat.narration.strip()}")
        # The scene's closing fade plays after its last beat — advance the clock past it so the next
        # scene's cues line up with where its video actually starts.
        cursor += SCENE_CLOSE_FADE_S
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
