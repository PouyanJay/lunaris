from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class VoiceUnavailableError(VideoPipelineError):
    """The voice toggle is ON but no validated ElevenLabs key is available to narrate.

    The toggle cannot be ON without a validated key (the config-validation contract, §0); when a
    voiced job still reaches the pipeline without one, it fails fast and clear rather than silently
    falling back to a silent video the user did not ask for (the vision-floor fail-fast stance).
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"job {job_id} requested narration but no ElevenLabs key is available "
            "(the voice toggle requires a validated key)"
        )
        self.job_id = job_id
