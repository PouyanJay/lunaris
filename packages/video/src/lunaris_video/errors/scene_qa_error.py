from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SceneQaError(VideoPipelineError):
    """Gate B verdict: a scene's visual defect survived the repair budget.

    Distinct from ``SceneRenderError`` (the scene renders fine — it is spatially wrong). Carries
    the unresolved defects so the job's failure record says what the gate saw, not just that it
    failed.
    """

    def __init__(self, scene_id: str, *, attempts: int, error_tail: str) -> None:
        super().__init__(f"scene {scene_id} failed visual QA after {attempts} attempts")
        self.scene_id = scene_id
        self.attempts = attempts
        self.error_tail = error_tail
