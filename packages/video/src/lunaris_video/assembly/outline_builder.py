from dataclasses import dataclass

from lunaris_video.assembly.scene_timing import SCENE_CLOSE_FADE_S
from lunaris_video.schemas.scene_contract import SceneContract
from lunaris_video.schemas.scene_contracts import SceneContracts
from lunaris_video.schemas.timing_manifest import TimingManifest


@dataclass(frozen=True)
class Chapter:
    """One scene surfaced as a navigable chapter, with its span on the concatenated timeline."""

    id: str
    title: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class TranscriptCue:
    """One spoken beat with its timed span on the concatenated timeline."""

    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class VideoOutline:
    """The Cinema outline of a ready video: navigable chapters + a timed transcript."""

    chapters: list[Chapter]
    transcript: list[TranscriptCue]


def _derived_title(scene: SceneContract) -> str:
    """A readable chapter title from the scene id's slug (``S3_self_similarity`` → ``Self
    similarity``) — the fallback when the planner authored none."""
    _, _, slug = scene.id.partition("_")
    return slug.replace("_", " ").capitalize() if slug else scene.id


def build_video_outline(contracts: SceneContracts, manifest: TimingManifest) -> VideoOutline:
    """Derive the Cinema outline from artifacts the pipeline already ships: the scene contracts
    (order, titles, narration) and the timing manifest (real per-beat durations).

    Chapters tile the concatenated timeline one per scene — each spans its beats' on-screen
    windows plus the closing fade the render plays after the scene — so they are contiguous and a
    click seeks to exactly where the scene begins. The transcript carries one cue per SPOKEN beat
    (a silent/estimate video yields none), timed on the same global cursor the caption builder
    uses, so cue clocks match the final MP4.
    """
    chapters: list[Chapter] = []
    transcript: list[TranscriptCue] = []
    cursor = 0.0
    for scene in contracts.scenes:
        scene_start = cursor
        timing_by_beat = {beat.id: beat for beat in manifest[scene.id].beats}
        for beat in scene.beats:
            timing = timing_by_beat[beat.id]
            start, end = cursor, cursor + timing.anim_s
            cursor = end
            if timing.audio and beat.narration.strip():
                transcript.append(TranscriptCue(start, end, beat.narration.strip()))
        # The closing fade plays after the scene's last beat — fold it into this chapter so the
        # next chapter starts exactly where the next scene's video does (no gaps).
        cursor += SCENE_CLOSE_FADE_S
        chapters.append(
            Chapter(
                id=scene.id,
                title=scene.title or _derived_title(scene),
                start_s=scene_start,
                end_s=cursor,
            )
        )
    return VideoOutline(chapters=chapters, transcript=transcript)
