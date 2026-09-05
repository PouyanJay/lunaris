from fastapi import APIRouter, Response, status

from ...dependencies import OptionalUserIdDep
from .dependencies import LiveSessionServiceDep
from .failure_mapping import raise_translated

router = APIRouter(prefix="/api/live/knowledge", tags=["live"])


@router.delete("/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_topic(
    graph_id: str,
    service: LiveSessionServiceDep,
    owner_id: OptionalUserIdDep,
) -> Response:
    """Forget what Lunaris has concluded about this learner on one topic (T5).

    204 with no body. The other half of the delete pair (U2): deleting a session stops keeping what
    the learner said, and this stops keeping what was concluded about them. Neither can do the
    other's job, because beliefs are keyed by graph and node with no session id in them.

    409 while a session on this map is still going: a session in progress writes the model back at
    the end of every turn, so a reset underneath one would be silently undone. The detail says to
    finish or leave that session first.

    Its own router rather than a route on the sessions one, because the subject is the map and not
    a session, and a `/api/live/sessions/...` path that took a graph id would read as a lie.
    """
    correlated = {"X-Graph-Id": graph_id}
    try:
        await service.forget(graph_id, owner_id=owner_id)
    except Exception as exc:
        raise_translated(exc, correlated, "live.knowledge.forget_failed", graph_id=graph_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=correlated)
