from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SceneRenderError(VideoPipelineError):
    """Gate A verdict: a scene exhausted its repair budget and still does not render.

    Carries what diagnosis needs (the scene and the LAST stack-trace tail); the workdir keeps
    every attempt's source on disk, so a failed job is debuggable without re-running it.
    """

    def __init__(self, scene_id: str, *, attempts: int, error_tail: str) -> None:
        super().__init__(f"scene {scene_id} failed to render after {attempts} attempts")
        self.scene_id = scene_id
        self.attempts = attempts
        self.error_tail = error_tail
