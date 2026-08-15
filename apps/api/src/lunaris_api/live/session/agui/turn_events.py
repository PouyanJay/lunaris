from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

from ag_ui.core import (
    BaseEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from lunaris_live.session import Session

from ..turn_beat import TurnBeat
from .layout_tool import LAYOUT_TOOL
from .session_snapshot import SessionSnapshot
from .surface_tool import SURFACE_TOOL


async def turn_events(
    turn: AsyncIterator[tuple[TurnBeat, str | Session]], *, thread_id: str, run_id: str
) -> AsyncIterator[BaseEvent]:
    """One run of a session, as the AG-UI events a CopilotKit client renders.

    The **only** frame sequence this transport produces, and both kinds of run are fed through it: a
    live turn, whose fragments arrive as the tutor writes them, and the replay a freshly-loaded tab
    makes, whose single fragment is the turn already in front of the learner. They differ in where
    the words come from and in nothing else, which is the point — a second sequence would be a
    second thing a client has to be written against, and the two would drift the first time one of
    them gained a frame.

    Translation lives on this side of the boundary rather than in ``lunaris_live``: the session
    package stays transport-agnostic, and AG-UI is a wire format, not a fact about teaching.

    ``thread_id`` and ``run_id`` come from the client and are echoed rather than minted: AG-UI
    correlates a stream to the run that asked for it by those two ids, and a client holding several
    runs on one thread cannot attach frames carrying ids it has never seen.
    """
    yield RunStartedEvent(thread_id=thread_id, run_id=run_id)

    # A message is opened before anything is known to be in it. The alternative — waiting for the
    # first fragment — leaves a client that has begun a run with nothing to attach the words to, and
    # leaves a *wordless* run with no message to close, so it waits.
    message_id = uuid4().hex
    yield TextMessageStartEvent(message_id=message_id, role="assistant")

    settled: Session | None = None
    try:
        async for beat, payload in turn:
            # Matched on the beat alone, exhaustively. An earlier version leaned on ``isinstance``
            # for the terminal case, which made a payload matching neither predicate vanish
            # silently — no frame, no error, no log — and T3 through T5 each add a producer to this
            # stream. A name that does not exist should be loud on the first run, not a state frame
            # that quietly never arrives.
            match beat:
                case TurnBeat.DELTA:
                    if not payload:
                        # ``TextMessageContentEvent`` refuses an empty delta, and rightly: a frame
                        # that says nothing is one every client has to learn to ignore.
                        continue
                    yield TextMessageContentEvent(message_id=message_id, delta=str(payload))
                case TurnBeat.SESSION:
                    settled = payload if isinstance(payload, Session) else None
                case _:
                    raise ValueError(f"{beat!r} is not a beat this transport knows how to render")
    except Exception:
        # The tutor's provider died halfway through a sentence, most plausibly. The message opened
        # above has to be **closed before the failure travels on**: a client holding an open message
        # reads it as a tutor still typing, so it would sit waiting through the very frame the
        # caller sends to stop it waiting. The failure itself is not swallowed — the router turns it
        # into a ``RUN_ERROR``, because by now the status is long spent.
        yield TextMessageEndEvent(message_id=message_id)
        raise

    yield TextMessageEndEvent(message_id=message_id)

    if settled is not None:
        # The card the director chose, after the words it follows: a quiz that appeared while the
        # tutor was still setting it up would be answered against half a sentence.
        for event in _surface_events(settled):
            yield event

        # Before ``RUN_FINISHED``, deliberately. A client that treats the end of a run as "settled"
        # would otherwise render the previous turn's state for the whole length of the next one.
        yield StateSnapshotEvent(
            snapshot=SessionSnapshot.of(settled).model_dump(by_alias=True, mode="json")
        )

    yield RunFinishedEvent(thread_id=thread_id, run_id=run_id)


def _surface_events(session: Session) -> Iterator[BaseEvent]:
    """The standing turn's two generative surfaces: the Tier 1 card (T3), then its layout (T5).

    Nothing at all when the turn has neither. That is every turn P2a stored (R4), and a client
    waiting on tool frames that never come would sit on a spinner over a session it can read
    perfectly well — so the absence has to be silence rather than an empty call.

    **The card goes first.** Tier 2's layout holds a *slot* for it, so a client drawing frames as
    they land has the card in hand by the time it is told where to put it. The other order would
    make the layout's first paint a hole.

    Each spec's arguments go out as a single ``TOOL_CALL_ARGS`` frame. They are already complete
    when the turn is built — these are deterministic specs, not a model writing JSON a token at a
    time — and splitting a finished object into fragments would only invite a client to render a
    half-parsed one.
    """
    standing = session.turns[-1] if session.turns else None
    if standing is None:
        return

    if standing.surface is not None:
        yield from _tool_call(SURFACE_TOOL, standing.surface.model_dump_json(by_alias=True))
    if standing.layout is not None:
        yield from _tool_call(LAYOUT_TOOL, standing.layout.model_dump_json(by_alias=True))


def _tool_call(name: str, arguments: str) -> Iterator[BaseEvent]:
    """One complete tool call, start to end, under its own id.

    A fresh id per call rather than one shared across the turn: AG-UI keys a call's arguments to its
    id, and two calls sharing one would have the second read as an amendment to the first.
    """
    call_id = uuid4().hex
    yield ToolCallStartEvent(tool_call_id=call_id, tool_call_name=name)
    yield ToolCallArgsEvent(tool_call_id=call_id, delta=arguments)
    yield ToolCallEndEvent(tool_call_id=call_id)
