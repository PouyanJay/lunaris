from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard
from pydantic import ValidationError

from .schema import Session, SessionSummary
from .session_format_error import SessionFormatError
from .stale_answer_error import StaleAnswerError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "live_sessions"

#: The statuses a session is done in: nothing more is taught and nothing more will be written.
_FINISHED = ("closed", "abandoned")


class SupabaseSessionStore:
    """The durable session store: Supabase Postgres, ``jsonb`` payload, lazy service-role client.

    Same shape as ``SupabaseGraphStore`` — lazy construction so the composition root needs no creds
    or network to build it, camelCase payload identical to the wire, and ``guard`` turning driver
    failures into ``PersistenceError``.

    Like a graph and unlike a Studio course, a session is **mutable**: every turn rewrites the head.
    So ``save`` upserts on ``id`` and the turns ride in the payload rather than in their own table.
    One row per session, rewritten per turn, is right while a session is bounded to 25-40 minutes
    (plan §6) and always read whole; a turns table earns its place when something wants to read one
    turn without the rest, which nothing does yet.
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env=self._url_env,
                service_key_env=self._service_key_env,
                purpose="persist sessions",
            )
        return self._client

    @guard("live_sessions upsert")
    def save(
        self, session: Session, *, owner_id: str | None = None, expect_turns: int | None = None
    ) -> None:
        """Write the session's head, optionally only if it is still the one the caller read.

        ``expect_turns`` turns this into a compare-and-set against ``turn_count``, which is why that
        column was lifted out of the payload in the first place. Two answers submitted at once both
        read the same head and both pass any in-memory staleness check; without the condition here
        the second write silently overwrites the first, losing a graded answer and the model calls
        that produced it. Postgres settles it: the second UPDATE matches no row.
        """
        client = self._ensure_client()
        row: dict[str, object] = {
            "id": session.session_id,
            "graph_id": session.graph_id,
            "status": session.status.value,
            # Lifted out of the payload because it is the one thing a resume needs to know without
            # parsing the whole session: how far the learner got.
            "turn_count": len(session.turns),
            "payload": session.model_dump(mode="json", by_alias=True),
        }
        if owner_id is not None:
            row["user_id"] = owner_id

        if expect_turns is None:
            client.table(_TABLE).upsert(row, on_conflict="id").execute()  # type: ignore[attr-defined]
            return

        query = client.table(_TABLE).update(row).eq("id", session.session_id)  # type: ignore[attr-defined]
        # Scoped both ways, like the read: the service-role client bypasses RLS, so an update that
        # only matched on the id could rewrite another learner's session.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        if not query.eq("turn_count", expect_turns).execute().data:
            raise StaleAnswerError(
                f"session {session.session_id} is no longer at {expect_turns} turns"
            )

    @guard("live_sessions load")
    def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        client = self._ensure_client()
        query = client.table(_TABLE).select("payload").eq("id", session_id)  # type: ignore[attr-defined]
        # Constrained in the query rather than checked after the read, and constrained EITHER WAY:
        # the service-role client bypasses RLS, so this is the only thing standing between one
        # learner's session and another's. An unscoped read matches only rows that are themselves
        # unowned rather than seeing everything — the store must not depend on the auth wiring above
        # it staying configured the way it is today.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.limit(1).execute().data
        if not rows:
            raise FileNotFoundError(session_id)
        try:
            return Session.model_validate(rows[0]["payload"])
        except ValidationError as exc:
            # Told apart from a backend failure because the two want opposite things from the
            # learner: an outage ends and is worth retrying, a row written by a schema this build no
            # longer understands does not. Undistinguished, ``guard`` would turn this into the same
            # "storage is having trouble" a reload is the right answer to. Live under a rolling
            # deploy, and the turn schema is still growing (T4 added ``run_id``; T5, T6 add more).
            raise SessionFormatError(f"session {session_id} is not in a readable format") from exc

    @guard("live_sessions has_open_on")
    def has_open_on(self, graph_id: str, *, owner_id: str | None = None) -> bool:
        """Whether this owner has an unfinished session on this map (T5).

        Read through ``live_sessions_graph_idx`` on ``(user_id, graph_id)``, and asked as its own
        question rather than by filtering a listing: the answer gates a destructive act, and a limit
        that hid one open session would make the guard a coin toss. One column, one row at most.
        """
        client = self._ensure_client()
        query = client.table(_TABLE).select("id").eq("graph_id", graph_id)  # type: ignore[attr-defined]
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.not_.in_("status", list(_FINISHED)).limit(1).execute().data
        return bool(rows)

    @guard("live_sessions ids_on")
    def session_ids_on(self, graph_id: str, *, owner_id: str | None = None) -> tuple[str, ...]:
        """Every session id this owner has on one map, through ``live_sessions_graph_idx``.

        One column, no payload: this is asked to decide whether anything is happening to the map
        right now, not to show anybody anything.
        """
        client = self._ensure_client()
        query = client.table(_TABLE).select("id").eq("graph_id", graph_id)  # type: ignore[attr-defined]
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        return tuple(row["id"] for row in query.execute().data or [])

    @guard("live_sessions delete")
    def delete(self, session_id: str, *, owner_id: str | None = None) -> None:
        """Remove one session row, scoped to its owner.

        Scoped in the DELETE itself rather than after a read, and either way, for the reason
        ``load`` gives at length: the service-role client bypasses RLS, so this predicate is the
        only thing standing between one learner's delete and another learner's transcript. A
        delete that only matched on the id would be a way to remove somebody else's session by
        guessing an id.

        The returned rows are what say whether anything matched, which is how a missing session
        becomes ``FileNotFoundError`` here rather than a silent success. Only the session row goes:
        `live_knowledge`, `live_materials` and `live_graphs` are keyed by graph, not by session,
        and forgetting what a learner demonstrated is its own verb (U2).
        """
        client = self._ensure_client()
        query = client.table(_TABLE).delete().eq("id", session_id)  # type: ignore[attr-defined]
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        if not query.execute().data:
            raise FileNotFoundError(session_id)

    @guard("live_sessions recent")
    def recent(self, *, owner_id: str | None = None, limit: int = 50) -> list[SessionSummary]:
        """This owner's sessions, newest first, read through the index built for exactly this.

        ``live_sessions_user_idx`` on ``(user_id, updated_at desc)`` has been there since Phase 2a
        and has never been read. The columns lifted out of the payload are what makes this a list
        query rather than twenty transcripts parsed to draw twenty rows: ``status`` and
        ``turn_count`` are already up here, and only ``topic`` and ``startedAt`` have to be reached
        for inside the json.
        """
        client = self._ensure_client()
        query = client.table(_TABLE).select(  # type: ignore[attr-defined]
            "id, graph_id, status, turn_count, updated_at, payload->>topic, payload->>startedAt"
        )
        # Scoped in the query, either way, for the reason ``load`` gives: the service-role client
        # bypasses RLS, so this is the only thing between one learner's history and another's.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.order("updated_at", desc=True).limit(limit).execute().data
        try:
            return [_summary_of(row) for row in rows]
        except (ValidationError, KeyError, TypeError) as exc:
            # Same split ``load`` makes, and the same reason: a row this build cannot read is not an
            # outage, and a reload is not the answer to it.
            raise SessionFormatError("a session row is not in a readable format") from exc


def _summary_of(row: dict) -> SessionSummary:
    """One selected row as a summary. ``startedAt`` keeps its camelCase: the payload is the wire
    JSON, so a json path into it reads the wire's own field names, not Python's."""
    return SessionSummary(
        session_id=row["id"],
        graph_id=row["graph_id"],
        topic=row["topic"],
        status=row["status"],
        turn_count=row["turn_count"],
        started_at=row["startedAt"],
        updated_at=row["updated_at"],
    )
