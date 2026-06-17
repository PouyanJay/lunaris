from enum import StrEnum
from typing import Self

from pydantic import ValidationError

from lunaris_video.errors import FactualGateError, SceneRenderError, VideoPipelineError


class VideoFailureKind(StrEnum):
    """The queryable taxonomy a failed video job is bucketed into (E1).

    Coarse on purpose — the caller also logs ``failure_class`` (the exact exception type), so a kind
    is never ambiguous. Sync and length no longer fail a job (they degrade best-effort since
    #100/#101), so they are deliberately absent. The worker logs ``classify(exc)`` on
    ``job_failed``; the C4 quality eval reuses the SAME classifier so a measured failure is bucketed
    exactly as a prod failure would be (one taxonomy, two readers).
    """

    FACTUAL = "factual"  # Gate C major: a smuggled / ungrounded figure (caught pre-render)
    RENDER = "render"  # Gate A: a scene exhausted its render-repair budget
    CODEGEN_PARSE = "codegen_parse"  # generated source never parsed (parse-repair exhausted)
    PIPELINE = "pipeline"  # any other VideoPipelineError
    INFRASTRUCTURE = "infrastructure"  # non-pipeline: queue / storage / unexpected

    @classmethod
    def classify(cls, exc: Exception) -> Self:
        """Bucket a job failure. Order matters: the specific ``VideoPipelineError`` subclasses are
        tested before the base.

        A pydantic ``ValidationError`` IS a ``ValueError``, but it is NOT the codegen parse path —
        it is a schema/structured-data failure (a corrupt stored artifact, or a planner whose
        structured output never validated), so it is bucketed ``INFRASTRUCTURE`` and ruled out
        first. ``CODEGEN_PARSE`` is then the bare ``ValueError`` that ``validate_scene_source``
        raises when generated Manim source will not parse — the dominant prod failure.
        """
        if isinstance(exc, FactualGateError):
            return cls.FACTUAL
        if isinstance(exc, SceneRenderError):
            return cls.RENDER
        if isinstance(exc, VideoPipelineError):
            return cls.PIPELINE
        if isinstance(exc, ValidationError):
            return cls.INFRASTRUCTURE
        if isinstance(exc, ValueError):
            return cls.CODEGEN_PARSE
        return cls.INFRASTRUCTURE
