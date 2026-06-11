from contextlib import nullcontext
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.logging import bind_request_id

from ..dependencies import ExplainBindingDep, ExplainThrottleDep, OptionalUserIdDep
from ..explain_throttle import ExplainDailyCapReachedError
from ..schemas import ExplainRequest, ExplainResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/explain", tags=["explain"])

# The per-day cap bucket for an unowned caller (auth off / single-user instance) — mirrors the
# build throttle's local bucket.
_LOCAL_OWNER_KEY = "__local__"


@router.post("", response_model=ExplainResponse)
async def explain_blob(
    payload: ExplainRequest,
    binding: ExplainBindingDep,
    throttle: ExplainThrottleDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> ExplainResponse:
    """Explain a blob (lesson content or a transcript artifact) in plain language.

    Tiered: a keyed caller is answered by Claude (``source: hosted``, uncapped); an unkeyed caller
    by the keyless server model (``source: server-fallback``) behind a per-user daily cap (429 when
    exhausted). Neither tier available → 503 (the web hides/disables the affordance via
    ``supportsExplain``). Runs inside the caller's own credential scope, so a vault tenant's key —
    never the platform's — answers their call. Only the content's length is ever logged.
    ``X-Request-Id`` correlates success and failure alike.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    # Headers set on ``response`` only ride the success path; the raised errors carry the id
    # explicitly so a failed explain is just as triangulatable as a successful one.
    response.headers["X-Request-Id"] = request_id
    correlated = {"X-Request-Id": request_id}
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Explanations are unavailable: no Anthropic key and no keyless tier.",
            headers=correlated,
        )
    if binding.source == "server-fallback":
        try:
            throttle.admit(owner_id or _LOCAL_OWNER_KEY)
        except ExplainDailyCapReachedError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
                headers=correlated,
            ) from exc
    # The tenant scope wraps only the model call; a vault caller's own keys answer it. No
    # credentials (auth off / single-user) → a no-op scope, i.e. the process environment.
    scope = (
        run_credentials(binding.credentials) if binding.credentials is not None else nullcontext()
    )
    try:
        with scope:
            explanation = await binding.explainer.explain(payload.content, payload.context)
    except Exception as exc:
        # Never log the content (it can be arbitrary); a failed model call degrades to a clean 503.
        logger.warning(
            "explain_failed",
            content_length=len(payload.content),
            source=binding.source,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't generate an explanation right now.",
            headers=correlated,
        ) from exc
    return ExplainResponse(explanation=explanation, source=binding.source)
