from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.session import (
    Session,
    SessionSummary,
)
from lunaris_runtime.logging import bind_request_id

from ...dependencies import OptionalUserIdDep
from .dependencies import LiveSessionServiceDep
from .failure_mapping import raise_translated
from .schemas import AnswerRequest, SessionStartRequest

router = APIRouter(prefix="/api/live/sessions", tags=["live"])


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartRequest,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Open a session and hand back its first turn: on a compiled map, or on a topic (U1).

    Answers 201 with the session already talking rather than an empty shell the surface then has to
    poll: a session that opens with nothing to show is a loading spinner with a database row behind
    it. On a map, that first turn is a lesson; on a topic, it is the interviewer's first question
    while the map compiles behind it (plan §6). ``X-Session-Id`` rides the response so a learner
    reporting "it went wrong" can name the session across every layer's logs.
    """
    # Minted here, and put on the response before the work: a header set only after success is
    # absent from exactly the failures somebody needs to report. Every raise below carries it
    # explicitly, because raising an HTTPException discards the response object built here.
    session_id = uuid4().hex
    response.headers["X-Session-Id"] = session_id
    correlated = {"X-Session-Id": session_id}
    try:
        if payload.topic is not None:
            return await service.start_placement(
                payload.topic, session_id=session_id, owner_id=owner_id
            )
        # The contract admits exactly one of the two, so a request without a topic has a map.
        assert payload.graph_id is not None
        return await service.start(payload.graph_id, session_id=session_id, owner_id=owner_id)
    except Exception as exc:
        _refuse(exc, correlated, "live.session.start_failed", session_id=session_id, missing="Map")


@router.post("/{session_id}/turns", response_model=Session)
async def answer_turn(
    session_id: str,
    payload: AnswerRequest,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Answer the criterion the last turn staged, and get the session back with its next turn.

    The whole session comes back rather than just the new turn: the answered turn changes too — it
    gains the learner's words and the verdict on them — and a surface patching two shapes together
    is a surface that can disagree with the row behind it.
    """
    correlated = {"X-Session-Id": session_id}
    try:
        session = await service.answer(
            session_id, payload.answer, answering_seq=payload.answering_seq, owner_id=owner_id
        )
    except Exception as exc:
        _refuse(
            exc, correlated, "live.session.answer_failed", session_id=session_id, missing="Session"
        )
    response.headers["X-Session-Id"] = session_id
    return session


@router.post("/{session_id}/advance", response_model=Session)
async def advance_session(
    session_id: str,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session | Response:
    """Move a warming session on, if its map has landed (P2c T2).

    The way out of the honest wait: while a session is warming (the interview is over, the map is
    not there yet) the surface polls this. 200 with the session when there was something to do —
    teaching began, or the session closed on a compile that failed — and also when the session is
    not warming at all (an answer got there first): the current row. **202 with no body** while it
    is still warming: not a turn, not an error, "ask again in a moment".
    """
    correlated = {"X-Session-Id": session_id}
    try:
        session = await service.advance(session_id, owner_id=owner_id)
    except Exception as exc:
        _refuse(
            exc, correlated, "live.session.advance_failed", session_id=session_id, missing="Session"
        )
    if session is None:
        return Response(status_code=status.HTTP_202_ACCEPTED, headers=correlated)
    response.headers["X-Session-Id"] = session_id
    return session


@router.post("/{session_id}/end", response_model=Session)
async def end_session(
    session_id: str,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Finish a session deliberately, with the ceremony intact (T3).

    200 with the closed session, whose last turn carries the recap, the mastery delta and the day
    to come back. Idempotent: a second press returns the session that already ended rather than
    paying for a second goodbye, because a stop button is a thing people double-click and this one
    costs a model call.
    """
    correlated = {"X-Session-Id": session_id}
    try:
        session = await service.end(session_id, owner_id=owner_id)
    except Exception as exc:
        _refuse(
            exc, correlated, "live.session.end_failed", session_id=session_id, missing="Session"
        )
    response.headers["X-Session-Id"] = session_id
    return session


@router.post("/{session_id}/discard", response_model=Session)
async def discard_session(
    session_id: str,
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> Session:
    """Leave a session, without a ceremony (T3).

    200 with the abandoned session. Nothing is recapped, nothing is scheduled and no model is
    called: leaving is not a teaching moment. Not a delete (U2) — the transcript is still the
    learner's to read, and removing it is its own deliberate act.
    """
    correlated = {"X-Session-Id": session_id}
    try:
        session = await service.discard(session_id, owner_id=owner_id)
    except Exception as exc:
        _refuse(
            exc, correlated, "live.session.discard_failed", session_id=session_id, missing="Session"
        )
    response.headers["X-Session-Id"] = session_id
    return session


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    service: LiveSessionServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> list[SessionSummary]:
    """This learner's own sessions, newest first (T2).

    Summaries, never transcripts: a learner looking over their sessions wants to recognise them,
    and sending twenty full teaching histories to draw twenty rows would be the wrong trade in
    every direction. Registered above ``/{session_id}`` for readability only; the paths cannot
    collide, since an empty id is not a path.

    No ``X-Session-Id`` here because it names no session. A fresh ``X-Request-Id`` carries the
    correlation instead, the way every other route that fans out does it, so a learner reporting
    "my sessions did not load" can still be found in the logs.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    return await service.recent(owner_id=owner_id)


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
    except Exception as exc:
        _refuse(
            exc, correlated, "live.session.read_failed", session_id=session_id, missing="Session"
        )
    response.headers["X-Session-Id"] = session_id
    return session


def _refuse(
    exc: Exception,
    correlated: dict[str, str],
    event: str,
    *,
    session_id: str,
    missing: str = "Session",
) -> NoReturn:
    """The one shape every session endpoint refuses in: not-found is 404 in the endpoint's own noun
    (a map, a session), and everything else is ``raise_translated``'s. Four endpoints carried this
    verbatim before the fourth arrived (P2c T2)."""
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{missing} not found", headers=correlated
        ) from exc
    raise_translated(exc, correlated, event, session_id=session_id)
