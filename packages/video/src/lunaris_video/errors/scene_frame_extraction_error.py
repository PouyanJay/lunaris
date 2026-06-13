from lunaris_video.errors.video_pipeline_error import VideoPipelineError


class SceneFrameExtractionError(VideoPipelineError):
    """ffprobe/ffmpeg could not produce a scene's QA frames — Gate B has nothing to look at.

    A pipeline-domain failure (a ``VideoPipelineError``), not a programming error: the worker
    settles the job FAILED and records this class name, distinct from a render or QA-verdict
    failure, so a triage knows the frames — not the scene — were the problem.
    """
