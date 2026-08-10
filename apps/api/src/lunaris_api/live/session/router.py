from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.session import Session, SessionFormatError, TutorUnavailableError
from lunaris_runtime.persistence import PersistenceError

from ...dependencies import OptionalUserIdDep
from .dependencies import LiveSessionServiceDep
from .schemas import SessionStartRequest

logger = structlog.get_logger()

router = APIRouter(prefix="/api/live/sessions", tags=["live"])

_UNAVAILABLE = "Live is having trouble reaching its storage. Try again shortly."

#: The tutor being down is a different outage from storage being down, and a learner can tell: one
#: means their session did not open, the other means it may not have been saved. Both end, so both
#: are worth retrying — which is why this is a 503 rather than a session opened with nothing in it.
_TUTOR_UNAVAILABLE = "Live's tutor could not reach its model. Try again shortly."

#: A row this build cannot parse never becomes readable by waiting, so it must not read as an
#: outage: "try again" on a permanently unreadable session is an invitation to reload forever.
_UNREADABLE = "This session was saved in a format Live can no longer read."


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartRequest,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Open a session on a compiled map and hand back its first turn.

    Answers 201 with the session already teaching rather than an empty shell the surface then has to
    poll: a session that opens with nothing to show is a loading spinner with a database row behind
    it. ``X-Session-Id`` rides the response so a learner reporting "it went wrong" can name the
    session across every layer's logs.
    """
    # Minted here, and put on the response before the work: a header set only after success is
    # absent from exactly the failures somebody needs to report. Every raise below carries it
    # explicitly, because raising an HTTPException discards the response object built here.
    session_id = uuid4().hex
    response.headers["X-Session-Id"] = session_id
    correlated = {"X-Session-Id": session_id}
    try:
        return await service.start(payload.graph_id, session_id=session_id, owner_id=owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Map not found", headers=correlated
        ) from exc
    except Exception as exc:
        # Logged with the traceback because nothing below the router does — the stores stay silent
        # and ``guard`` only translates. Without this an outage is a bare 500 with no way to tell
        # what broke, on the path where a learner has just lost a session before it began.
        logger.warning("live.session.start_failed", session_id=session_id, exc_info=True)
        if (translated := _translate(exc, correlated)) is not None:
            raise translated from exc
        raise


@router.get("/{session_id}", response_model=Session)
async def read_session(
    session_id: str,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Re-read a session, so a reloaded tab lands back where the learner was (U2).

    Another learner's session is 404, not 403 — a session's existence is itself owner-scoped
    information, the same posture Phase 1 took for graphs.
    """
    correlated = {"X-Session-Id": session_id}
    try:
        session = await service.load(session_id, owner_id=owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found", headers=correlated
        ) from exc
    except Exception as exc:
        logger.warning("live.session.read_failed", session_id=session_id, exc_info=True)
        if (translated := _translate(exc, correlated)) is not None:
            raise translated from exc
        raise
    response.headers["X-Session-Id"] = session_id
    return session


def _translate(exc: Exception, correlated: dict[str, str]) -> HTTPException | None:
    """The HTTP answer to a failure a learner could plausibly act on, or ``None`` to let it fly.

    One place, because the two entry points fail in the same ways and drifting apart would mean a
    learner learning what "try again" means from whichever endpoint they hit first. Ordered
    deliberately: ``SessionFormatError`` IS a ``PersistenceError``, and reading as a retryable
    outage is exactly the mistake it exists to prevent.
    """
    if isinstance(exc, SessionFormatError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_UNREADABLE,
            headers=correlated,
        )
    if isinstance(exc, TutorUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_TUTOR_UNAVAILABLE,
            headers=correlated,
        )
    if isinstance(exc, PersistenceError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
            headers=correlated,
        )
    return None
