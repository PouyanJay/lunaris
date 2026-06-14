from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SyncGateError(VideoPipelineError):
    """Gate D verdict: a beat's frame at its audio midpoint doesn't show what its narration says.

    Narrated-only: the audio-drives-video render makes sync deterministic by construction, so a
    mismatch is a codegen / scene-quality case the pipeline first tries to recover by re-planning
    plainer (easier-to-sync) scenes — only a SECOND miss fails the job (the whole video, never a
    narration/visual mismatch shipped: worse for a voiced video than an honest failure). ``reason``
    carries the vision model's account of the mismatch for the failure record; ``user_detail`` (set
    on the retry-exhausted miss) is the owner-safe, actionable line the reader shows.
    """

    def __init__(self, beat_id: str, *, reason: str, user_detail: str | None = None) -> None:
        super().__init__(f"beat {beat_id} failed the sync gate: {reason}", user_detail=user_detail)
        self.beat_id = beat_id
        self.reason = reason
