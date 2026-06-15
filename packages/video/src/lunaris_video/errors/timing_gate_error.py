from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class TimingGateError(VideoPipelineError):
    """Gate 1 verdict: a scene's rendered video is not as long as its audio timeline.

    The timeline is the sum of the scene's beat windows (``total_s``) plus the closing fade. When it
    doesn't match — a beat's animations overran their window, or the closing fade is missing/extra —
    the narration would drift against the visuals, and the error compounds across
    scenes. Deterministic (one ffprobe, no model call) and voiced-only; ``VideoPipeline.produce``
    catches it to deliver the silent version, exactly like a Gate D desync.
    """

    def __init__(self, scene_id: str, *, expected: float, actual: float) -> None:
        super().__init__(
            f"scene {scene_id} rendered {actual:.3f}s but its timeline is {expected:.3f}s "
            "— a beat overran its window or the closing fade is wrong"
        )
        self.scene_id = scene_id
        self.expected = expected
        self.actual = actual
