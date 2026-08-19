from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard
from pydantic import ValidationError

from .schema import Session
from .session_format_error import SessionFormatError
from .stale_answer_error import StaleAnswerError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "live_sessions"


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
