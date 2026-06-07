import os
from datetime import UTC, datetime

from lunaris_runtime.schema import Course

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "courses"


class SupabaseCourseStore:
    """The durable course store: Supabase Postgres (a ``jsonb`` payload), lazy service-role client.

    Mirrors ``SupabaseRunStore`` — the service-role client bypasses RLS (the ``courses`` table is
    RLS-enabled with no policies, server-only), and is built lazily on first use, so construction
    needs no creds and no network (the composition root can build it unconditionally). Synchronous
    on purpose: the supabase-py client is sync, and async callers off-load the blocking call via
    ``asyncio.to_thread`` (the harness ``finalize_course`` tool already does), so this presents the
    same sync surface as the file-backed ``CourseStore``.

    The payload is the camelCase Course wire JSON — the same bytes the file store wrote — so a
    course persisted by either store reads back identically. ``created_at`` is owned by the DB
    (``default now()``); ``updated_at`` is stamped on every ``save``.
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
        # An injected client (tests) skips lazy construction; production leaves it None so the
        # service-role client is built from the environment on first use.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot persist courses"
                )
            self._client = create_client(url, key)
        return self._client

    def save(self, course: Course) -> None:
        client = self._ensure_client()
        # Upsert so re-finalizing the same course_id REPLACES its row (parity with the file store's
        # overwrite). The payload is the by-alias dump in JSON mode (datetimes/enums → JSON-native),
        # i.e. the same shape model_dump_json(by_alias=True) writes to disk.
        row = {
            "id": course.id,
            "payload": course.model_dump(by_alias=True, mode="json"),
            "status": course.status.value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        client.table(_TABLE).upsert(row).execute()  # type: ignore[attr-defined]

    def load(self, course_id: str) -> Course:
        client = self._ensure_client()
        response = (
            client.table(_TABLE)  # type: ignore[attr-defined]
            .select("payload")
            .eq("id", course_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            # The store-agnostic not-found signal the API service catches (the file store raises the
            # same when the file is missing), so callers need no store-specific handling.
            raise FileNotFoundError(course_id)
        return Course.model_validate(rows[0]["payload"])

    def delete(self, course_id: str) -> bool:
        client = self._ensure_client()
        # Ask PostgREST for an exact count so "did anything get deleted?" doesn't depend on the
        # client's implicit return-representation default. Mirrors SupabaseRunStore.delete.
        response = (
            client.table(_TABLE).delete(count="exact").eq("id", course_id).execute()  # type: ignore[attr-defined]
        )
        return (response.count or 0) > 0
