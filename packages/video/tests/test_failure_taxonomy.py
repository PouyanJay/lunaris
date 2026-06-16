"""The video failure taxonomy (`VideoFailureKind.classify`) — the shared classifier the worker logs
on `job_failed` and the C4 quality eval buckets failures with. One taxonomy, two readers, so a
measured failure is taxonomised exactly as a prod failure would be."""

import pytest
from lunaris_video.errors import FactualGateError, SceneRenderError, VideoPipelineError
from lunaris_video.worker.failure_taxonomy import VideoFailureKind
from pydantic import BaseModel, ValidationError


def _validation_error() -> ValidationError:
    class _M(BaseModel):
        x: int

    try:
        _M.model_validate({"x": "not-an-int"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")  # pragma: no cover


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (FactualGateError("S2", unsupported=["7"], detail="d"), VideoFailureKind.FACTUAL),
        (SceneRenderError("S1", attempts=4, error_tail="boom"), VideoFailureKind.RENDER),
        (VideoPipelineError("generic pipeline failure"), VideoFailureKind.PIPELINE),
        # A pydantic ValidationError IS a ValueError but is ruled out FIRST as a schema failure,
        # never the codegen-parse bucket.
        (_validation_error(), VideoFailureKind.INFRASTRUCTURE),
        # The bare ValueError validate_scene_source raises when generated Manim won't parse.
        (ValueError("source does not parse: unterminated string"), VideoFailureKind.CODEGEN_PARSE),
        (RuntimeError("queue is down"), VideoFailureKind.INFRASTRUCTURE),
    ],
)
def test_classify_buckets_each_failure(exc: Exception, expected: VideoFailureKind) -> None:
    assert VideoFailureKind.classify(exc) is expected
