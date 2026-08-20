from typing import Protocol

from ..schema import Session, SessionSummary


class ISessionStore(Protocol):
    """Persistence for a learner's sessions.

    Synchronous because the durable implementation is supabase-py, which is; callers hop it to a
    thread rather than this protocol pretending to be async. Mirrors ``IGraphStore`` exactly, for
    the same reason it did: the in-memory and Supabase implementations have to be substitutable
    without a caller knowing which it has.

    ``owner_id`` is the authenticated learner. ``load`` raises ``FileNotFoundError`` when there is
    no such session **for that owner** — another learner's session is not-found rather than
    forbidden, because its existence is itself owner-scoped information.

    ``expect_turns`` makes a save a compare-and-set: the write lands only if the stored session is
    still the length the caller read. It is what stops two answers submitted at once from silently
    losing one — both would read the same head, both would pass an in-memory staleness check, and
    the second write would overwrite the first along with the model calls that produced it. ``None``
    means an unconditional write, which is right exactly once: when the session is created.
    Raises ``StaleAnswerError`` when the row has moved on.
    """

    def save(
        self, session: Session, *, owner_id: str | None = None, expect_turns: int | None = None
    ) -> None: ...

    def load(self, session_id: str, *, owner_id: str | None = None) -> Session: ...

    def recent(self, *, owner_id: str | None = None, limit: int = 50) -> list[SessionSummary]:
        """This owner's sessions, most recently moved first, as summaries rather than transcripts.

        Scoped the same way ``load`` is, and for a sharper reason: a list is where a scoping mistake
        shows a learner somebody else's teaching history all at once rather than one row of it.
        """
        ...
