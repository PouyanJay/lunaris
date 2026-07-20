from lunaris_video.assembly.scene_timing import walk_scene_timeline
from lunaris_video.models.video_outline import OutlineChapter, TranscriptCue, VideoOutline
from lunaris_video.schemas.scene_contract import SceneContract
from lunaris_video.schemas.scene_contracts import SceneContracts
from lunaris_video.schemas.timing_manifest import TimingManifest


def _chapter_title(scene: SceneContract) -> str:
    """The scene's authored title, else a readable label from its id slug (``S3_self_similarity``
    → ``Self similarity``) — the fallback for a scene with no planner title (pre-Cinema videos)."""
    if scene.title:
        return scene.title
    _, _, slug = scene.id.partition("_")
    return slug.replace("_", " ").capitalize() if slug else scene.id


def build_video_outline(contracts: SceneContracts, manifest: TimingManifest) -> VideoOutline:
    """Derive the Cinema outline from artifacts the pipeline already ships: the scene contracts
    (order, titles, narration) and the timing manifest (real per-beat durations).

    Chapters tile the concatenated timeline one per scene (its beats + the closing fade, so a click
    seeks to exactly where the scene begins); the transcript carries one cue per SPOKEN beat (a
    silent/estimate video yields none). Both ride ``walk_scene_timeline``, so their clocks match
    the caption track and the final MP4.
    """
    chapters: list[OutlineChapter] = []
    transcript: list[TranscriptCue] = []
    for span in walk_scene_timeline(contracts.scenes, manifest):
        chapters.append(
            OutlineChapter(span.scene.id, _chapter_title(span.scene), span.start_s, span.end_s)
        )
        for beat_span in span.beats:
            if beat_span.spoken:
                transcript.append(
                    TranscriptCue(
                        beat_span.start_s, beat_span.end_s, beat_span.beat.narration.strip()
                    )
                )
    return VideoOutline(chapters=chapters, transcript=transcript)
