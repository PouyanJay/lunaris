class VideoPipelineError(Exception):
    """Base for every failure the video pipeline raises — the worker settles the job FAILED."""
