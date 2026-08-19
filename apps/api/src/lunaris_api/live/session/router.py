from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.session import (
    Session,
)

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
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Map not found", headers=correlated
        ) from exc
    except Exception as exc:
        raise_translated(exc, correlated, "live.session.start_failed", session_id=session_id)


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
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found", headers=correlated
        ) from exc
    except Exception as exc:
        raise_translated(exc, correlated, "live.session.answer_failed", session_id=session_id)
    response.headers["X-Session-Id"] = session_id
    return session


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
        raise_translated(exc, correlated, "live.session.read_failed", session_id=session_id)
    response.headers["X-Session-Id"] = session_id
    return session
