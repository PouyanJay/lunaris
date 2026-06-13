from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class FactualGateError(VideoPipelineError):
    """Gate C verdict: a scene asserts a figure or comparison no cited claim supports.

    The video may say only what the lesson's verified claims prove (cross-cutting principle 2), so
    this fails the job clean rather than loosening the gate. ``unsupported`` names the exact
    smuggled figures so the failure record says what the gate caught, not just that it fired.
    """

    def __init__(self, scene_id: str, *, unsupported: list[str], detail: str) -> None:
        super().__init__(f"scene {scene_id} failed the factual gate: {detail}")
        self.scene_id = scene_id
        self.unsupported = unsupported
