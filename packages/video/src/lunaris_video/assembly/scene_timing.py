from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from lunaris_video.schemas.beat import Beat
from lunaris_video.schemas.scene_contract import SceneContract
from lunaris_video.schemas.timing_manifest import TimingManifest

# The on-screen seconds each scene spends fading out AFTER its last beat. The pinned skill ends each
# scene with ``clear_scene(scene, run_time=0.7)`` — a FadeOut of all mobjects for clean concat
# boundaries — rendered after the beat timeline, so a scene's video is this much longer than the sum
# of its beat windows (``total_s``). The audio mix and the caption clock MUST add the same gap after
# each scene, or audio/captions drift this far ahead of the video at every scene boundary, and the
# error compounds across scenes. The deterministic length gate asserts each scene's render lands on
# ``total_s + SCENE_CLOSE_FADE_S`` (within frame quantization), so this is the single source of
# truth for the closing-fade length across mix, captions, and the gate. It MUST track
# ``clear_scene``'s default run_time in the pinned ``assets/style_tokens.py`` (a test pins the two).
SCENE_CLOSE_FADE_S = 0.7


@dataclass(frozen=True)
class BeatSpan:
    """One beat's window on the concatenated timeline. ``spoken`` is True only for a beat that
    both carries a synthesized clip and has narration — the beats captions/transcripts render."""

    beat: Beat
    start_s: float
    end_s: float
    spoken: bool


@dataclass(frozen=True)
class SceneSpan:
    """One scene's window on the concatenated timeline (its beats plus the closing fade), and its
    beats' spans. ``end_s`` includes ``SCENE_CLOSE_FADE_S`` so scenes tile contiguously."""

    scene: SceneContract
    start_s: float
    end_s: float
    beats: list[BeatSpan]


def walk_scene_timeline(
    scenes: Iterable[SceneContract], manifest: TimingManifest
) -> Iterator[SceneSpan]:
    """Walk the scenes on the GLOBAL timeline of the concatenated video, in order: a cursor
    accumulates each beat's ``anim_s`` and then ``SCENE_CLOSE_FADE_S`` after every scene (the fade
    the render plays after a scene's beats). This is the single source of truth for where each
    scene and beat plays in the final MP4 — captions, the Cinema outline, and the mix all read it,
    so their clocks can never drift apart.
    """
    cursor = 0.0
    for scene in scenes:
        scene_start = cursor
        timing_by_beat = {timing.id: timing for timing in manifest[scene.id].beats}
        beat_spans: list[BeatSpan] = []
        for beat in scene.beats:
            timing = timing_by_beat[beat.id]
            start, end = cursor, cursor + timing.anim_s
            cursor = end
            beat_spans.append(
                BeatSpan(beat, start, end, spoken=bool(timing.audio and beat.narration.strip()))
            )
        cursor += SCENE_CLOSE_FADE_S
        yield SceneSpan(scene, scene_start, cursor, beat_spans)
