"""The device-bridge endpoints: how the learner's tab serves a device-compute build's completions.

The tab long-polls GET ``/api/runs/{run_id}/bridge/requests`` for parked completions, runs each on
its on-device model, and posts the text back via POST ``/api/runs/{run_id}/bridge/results``. Both
are scoped like every run surface: an unknown run — or another user's — is a 404.
"""

from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import DeviceBridgeRegistryDep, OptionalUserIdDep
from ..schemas.bridge import BridgeMessageView, BridgeRequestView, BridgeResultRequest

logger = structlog.get_logger()

router = APIRouter(prefix="/api/runs", tags=["device-bridge"])

# Long-poll bounds: the default keeps a poll comfortably under common proxy idle timeouts while
# letting the tab hold one request open instead of hammering; the cap stops a client from parking
# requests for minutes.
POLL_WAIT_DEFAULT_S = 25.0
POLL_WAIT_MAX_S = 30.0

# Run ids are uuid4().hex (32 chars); bounding the path param keeps an arbitrarily long hostile
# value out of lookups and logs (the input-validation standard every user-controlled key follows).
_RUN_ID_MAX = 64

_RunIdPath = Annotated[str, Path(min_length=1, max_length=_RUN_ID_MAX)]


@router.get("/{run_id}/bridge/requests", response_model=list[BridgeRequestView])
async def claim_bridge_requests(
    run_id: _RunIdPath,
    registry: DeviceBridgeRegistryDep,
    owner_id: OptionalUserIdDep,
    response: Response,
    wait: float = Query(default=POLL_WAIT_DEFAULT_S, ge=0, le=POLL_WAIT_MAX_S),
) -> list[BridgeRequestView]:
    """Long-poll the run's parked completions (the tab's work feed).

    An empty list is a normal answer — nothing was queued within the window and the tab simply
    polls again, never an error. 404 when the run has no live bridge: unknown, finished, not a
    device build, or another user's — indistinguishable by design (no existence leak). A
    request_id is bound + returned in ``X-Request-Id`` for cross-layer log correlation.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    bridge = registry.lookup(run_id, owner_id)
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No bridge for this run",
            headers={"X-Request-Id": request_id},
        )
    claimed = await bridge.claim(wait_s=wait)
    if claimed:
        logger.info("device_bridge_requests_claimed", run_id=run_id, count=len(claimed))
    return [
        BridgeRequestView(
            request_id=request.request_id,
            messages=[BridgeMessageView(**message) for message in request.messages],
        )
        for request in claimed
    ]


@router.post("/{run_id}/bridge/results", status_code=status.HTTP_204_NO_CONTENT)
async def post_bridge_result(
    run_id: _RunIdPath,
    payload: BridgeResultRequest,
    registry: DeviceBridgeRegistryDep,
    owner_id: OptionalUserIdDep,
) -> Response:
    """Settle one parked completion with the tab's text. 204 on success; 404 when the run has no
    live bridge; 409 when the request id is unknown or already answered. A request_id is bound +
    returned in ``X-Request-Id`` for cross-layer log correlation."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    headers = {"X-Request-Id": request_id}
    bridge = registry.lookup(run_id, owner_id)
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No bridge for this run", headers=headers
        )
    if not bridge.resolve(payload.request_id, payload.text):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unknown or already-answered request",
            headers=headers,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)
