from lunaris_video.assembly.scene_timing import walk_scene_timeline
from lunaris_video.models.video_outline import OutlineChapter, TranscriptCue, VideoOutline
from lunaris_video.schemas.scene_contract import SceneContract
from lunaris_video.schemas.scene_contracts import SceneContracts
from lunaris_video.schemas.timing_manifest import TimingManifest

_MAX_CHAPTER_KEY_TERMS = 8


def _chapter_title(scene: SceneContract) -> str:
    """The scene's authored title, else a readable label from its id slug (``S3_self_similarity``
    → ``Self similarity``) — the fallback for a scene with no planner title (pre-Cinema videos)."""
    if scene.title:
        return scene.title
    _, _, slug = scene.id.partition("_")
    return slug.replace("_", " ").capitalize() if slug else scene.id


def _chapter_key_terms(scene: SceneContract) -> tuple[str, ...]:
    """The scene's notable on-screen objects, cleaned, deduped (order-preserving) and capped — the
    per-chapter key-term signal the reader matches resources against and highlights."""
    terms: list[str] = []
    for obj in scene.objects:
        term = obj.strip()
        if term and term not in terms:
            terms.append(term)
        if len(terms) >= _MAX_CHAPTER_KEY_TERMS:
            break
    return tuple(terms)


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
            OutlineChapter(
                id=span.scene.id,
                title=_chapter_title(span.scene),
                start_s=span.start_s,
                end_s=span.end_s,
                key_terms=_chapter_key_terms(span.scene),
            )
        )
        for beat_span in span.beats:
            if beat_span.spoken:
                transcript.append(
                    TranscriptCue(
                        beat_span.start_s, beat_span.end_s, beat_span.beat.narration.strip()
                    )
                )
    return VideoOutline(chapters=chapters, transcript=transcript)
