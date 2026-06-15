from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SyncGateError(VideoPipelineError):
    """Gate D verdict: a beat's frame at its midpoint doesn't show what its narration says.

    Narrated-only: raised by the per-scene Gate D repair loop when a beat cannot be synced within
    the repair budget. ``VideoPipeline.produce`` catches this to deliver the clean SILENT version
    (rather than ship a narration/visual mismatch — worse for a voiced video than no narration at
    all), flagging it on provenance. ``reason`` carries the vision model's account of the mismatch
    for the log. ``user_detail`` is unused on this path but kept on ``VideoPipelineError`` for
    consistency with the error hierarchy.
    """

    def __init__(self, beat_id: str, *, reason: str, user_detail: str | None = None) -> None:
        super().__init__(f"beat {beat_id} failed the sync gate: {reason}", user_detail=user_detail)
        self.beat_id = beat_id
        self.reason = reason
