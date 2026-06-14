from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SyncGateError(VideoPipelineError):
    """Gate D verdict: a beat's frame at its audio midpoint doesn't show what its narration says.

    Narrated-only and fail-clean: the audio-drives-video render makes sync deterministic by
    construction, so a mismatch is a codegen bug or a re-plan case — the job fails with the beat
    named rather than looping a repair (the V6 regenerate path owns the fix, mirroring Gate C).
    ``reason`` carries the vision model's account of the mismatch for the failure record.
    """

    def __init__(self, beat_id: str, *, reason: str) -> None:
        super().__init__(f"beat {beat_id} failed the sync gate: {reason}")
        self.beat_id = beat_id
        self.reason = reason
