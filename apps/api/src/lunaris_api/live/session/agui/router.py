from collections.abc import AsyncIterator, Sequence

import structlog
from ag_ui.core import Message, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from lunaris_live.session import Session
from lunaris_runtime.logging import bind_run_id

from ....dependencies import OptionalUserIdDep
from ..dependencies import LiveSessionServiceDep
from ..failure_mapping import raise_translated
from ..service import LiveSessionService
from ..turn_beat import TurnBeat
from .replayed_turn import replayed_turn
from .turn_events import turn_events

logger = structlog.get_logger()

router = APIRouter(prefix="/api/live/sessions", tags=["live"])

#: What a run has to say, before it is translated into frames. Named because three signatures in
#: this module carry it and the spelled-out form pushes each of them onto four lines.
type _TurnStream = AsyncIterator[tuple[TurnBeat, str | Session]]

#: Proxies that buffer a response defeat the entire point of streaming a turn — the learner waits
#: the full turn and then gets it all at once, which is P2a's behaviour with more moving parts.
#: Title-Case to match ``X-Session-Id`` and the rest of the codebase's headers; HTTP does not care,
#: readers of a diff do.
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/{session_id}/agui")
async def stream_session(
    session_id: str,
    payload: RunAgentInput,
    service: LiveSessionServiceDep,
    owner_id: OptionalUserIdDep,
) -> StreamingResponse:
    """Run a session turn as an AG-UI event stream.

    The additive half of P2b's transport (U2): ``POST /turns`` and ``GET /{id}`` stay the durable
    open/answer/resume path, and this is the surface that can narrate a turn while it happens. A
    dropped stream therefore costs nothing — the session is a row, and re-reading it is the
    recovery, exactly as Phase 1 settled for the compile stream.

    Two kinds of run arrive here and the difference is whether the learner has said anything. A run
    carrying their message takes the next turn; a run carrying none is what a freshly-loaded tab
    makes, and it replays the turn already in front of them. Grading silence as an answer would be
    the worse default by far: every grader reads an empty answer as a miss, so a reload would move
    the belief on evidence the learner never gave.

    The work is set up **before** the response begins, so a session that does not exist is a 404
    and one a run is trying to *answer* after it closed is a 409 — the status has not left yet, and
    making every client parse a success to discover a refusal is the shape that mistake takes. The
    409 is conditional on the run carrying an answer, deliberately: a closed session still
    replays, because reading one back is exactly what ``GET /{id}`` is for and a learner re-opening
    a finished session should see how it ended rather than an error.
    """
    correlated = {"X-Session-Id": session_id}
    # Bound before the load, so a run that dies reading the session is still findable, and bound
    # with the *client's* id (R5): this run began in a browser and crossed a Node runtime to get
    # here, so an id minted on this side would leave three runtimes' logs with no shared key.
    bind_run_id(payload.run_id, session_id=session_id, thread_id=payload.thread_id)
    try:
        turn = await _turn_for(payload, service, session_id=session_id, owner_id=owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found", headers=correlated
        ) from exc
    except Exception as exc:
        raise_translated(exc, correlated, "live.agui.run_setup_failed", session_id=session_id)

    encoder = EventEncoder()
    # The content type comes from the encoder rather than a constant of our own: it already accepts
    # an ``accept`` argument for future negotiation (SSE vs a binary wire), and two places naming
    # the wire format is how they come to disagree about it.
    return StreamingResponse(
        _frames(turn, payload, encoder),
        media_type=encoder.get_content_type(),
        headers={**correlated, **_STREAM_HEADERS},
    )


async def _turn_for(
    payload: RunAgentInput,
    service: LiveSessionService,
    *,
    session_id: str,
    owner_id: str | None,
) -> _TurnStream:
    """What this run has to say, as the tagged stream ``turn_events`` renders.

    Awaited rather than deferred into the response body: everything that can refuse a turn — the
    session missing, the owner's budget spent, the session already closed — happens in here, and it
    can only be a status while the status line is still available.
    """
    if (answer := _answer_in(payload.messages)) is not None:
        return await service.stream_answer(
            session_id, answer, run_id=payload.run_id, owner_id=owner_id
        )
    return replayed_turn(await service.load(session_id, owner_id=owner_id))


def _answer_in(messages: Sequence[Message]) -> str | None:
    """The learner's answer, or ``None`` when this run carries none.

    The *last* user message, not the first: CopilotKit sends the whole thread on every run, so the
    earlier ones are answers already graded, and taking them again would re-score a session's
    history every turn. Blank content counts as nothing said — a client that sends an empty composer
    must not be able to have silence marked as a wrong answer.
    """
    said = next((m.content for m in reversed(messages) if m.role == "user" and m.content), None)
    if said is None:
        return None
    return said.strip() or None


async def _frames(
    turn: _TurnStream, payload: RunAgentInput, encoder: EventEncoder
) -> AsyncIterator[str]:
    """This run's events, encoded, with a mid-stream failure delivered as a frame.

    Lifted out of the endpoint so each reads at one level: the endpoint sets the work up and
    answers, this produces the body. They also fail in genuinely different ways — before the
    response has begun a failure is still a status, and after it the status is spent — which is
    easier to keep straight when the two are not interleaved in one function.
    """
    try:
        async for event in turn_events(turn, thread_id=payload.thread_id, run_id=payload.run_id):
            yield encoder.encode(event)
    except Exception:
        # Once the 200 has left, a failure can only be a *frame*, and Phase 1 settled this shape for
        # the compile stream. Without it the client sees a stream that simply stops —
        # indistinguishable from a tutor still thinking, so it waits rather than saying anything.
        # This is the live turn's real failure path: a tutor or grader that dies mid-turn.
        logger.warning("live.agui.run_failed", exc_info=True)
        yield encoder.encode(
            RunErrorEvent(message="The session could not be streamed.", code="run_failed")
        )
        return
    # No explicit ids: this line rides the contextvars binding in the endpoint, so the correlation
    # test proves the run really propagated rather than proving it was threaded through by hand.
    #
    # The binding survives into here because Starlette runs the response body in the same task as
    # the endpoint (and, on its legacy path, copies the context into the child task) — documented
    # behaviour of the primitive rather than an accident of where the bind sits. The guard against
    # a future BaseHTTPMiddleware breaking that is tests/test_streaming_correlation_guard.py.
    logger.info("live.agui.run_finished")
