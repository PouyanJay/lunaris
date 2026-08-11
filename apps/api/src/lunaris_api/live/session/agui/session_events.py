from collections.abc import Iterator
from uuid import uuid4

from ag_ui.core import (
    BaseEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from lunaris_live.session import Session


def session_events(session: Session, *, thread_id: str, run_id: str) -> Iterator[BaseEvent]:
    """One session's latest turn, as the AG-UI events a CopilotKit client renders.

    A pure function over the session, deliberately: the event *sequence* is the contract the browser
    is written against, and keeping it out of the router means it can be pinned without a socket.
    Translation lives on this side of the boundary rather than in ``lunaris_live`` — the session
    package stays transport-agnostic, and AG-UI is a wire format, not a fact about teaching.

    ``thread_id`` and ``run_id`` come from the client and are echoed rather than minted: AG-UI
    correlates a stream to the run that asked for it by those two ids, and a client holding several
    runs on one thread cannot attach frames carrying ids it has never seen.

    Phase 2b T1 streams what the turn already said. Driving a *live* turn — the tutor's words
    arriving as they are written — is T2; the frame sequence below is the one that will carry it,
    which is the point of settling it first.
    """
    yield RunStartedEvent(thread_id=thread_id, run_id=run_id)

    # A turn always has words (``SessionTurn.tutor`` is ``min_length=1``), so the empty case here is
    # a session with no turns at all — not a silent turn, which cannot be constructed.
    taught = session.turns[-1].tutor if session.turns else ""
    # A message is opened even when there is nothing to say. The alternative — skipping the frames
    # entirely — leaves a client that has begun a run with no message to close, and it waits.
    message_id = uuid4().hex
    yield TextMessageStartEvent(message_id=message_id, role="assistant")
    if taught:
        yield TextMessageContentEvent(message_id=message_id, delta=taught)
    yield TextMessageEndEvent(message_id=message_id)

    yield RunFinishedEvent(thread_id=thread_id, run_id=run_id)
