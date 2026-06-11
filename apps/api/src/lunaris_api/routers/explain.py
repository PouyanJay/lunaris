from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import ExplainerDep
from ..schemas import ExplainRequest, ExplainResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/explain", tags=["explain"])


@router.post("", response_model=ExplainResponse)
async def explain_blob(
    payload: ExplainRequest, explainer: ExplainerDep, response: Response
) -> ExplainResponse:
    """Explain a transcript blob (JSON/code/data) in plain language.

    Available only with a reachable Anthropic key. Without one the dependency is ``None`` and the
    route fails closed with a 503 (the web hides the affordance via ``supportsExplain``).
    The request content is bounded by the schema; only its length is logged, never the content.
    ``X-Request-Id`` correlates the call across the logs (correlation everywhere).
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    # Headers set on ``response`` only ride the success path; the raised errors carry the id
    # explicitly so a failed explain is just as triangulatable as a successful one.
    response.headers["X-Request-Id"] = request_id
    correlated = {"X-Request-Id": request_id}
    if explainer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Explanations are unavailable: no Anthropic key is configured.",
            headers=correlated,
        )
    try:
        explanation = await explainer.explain(payload.content, payload.context)
    except Exception as exc:
        # Never log the content (it can be arbitrary); a failed model call degrades to a clean 503.
        logger.warning("explain_failed", content_length=len(payload.content), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't generate an explanation right now.",
            headers=correlated,
        ) from exc
    return ExplainResponse(explanation=explanation)
