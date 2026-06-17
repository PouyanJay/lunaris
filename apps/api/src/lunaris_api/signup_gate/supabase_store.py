import asyncio
import os
from datetime import UTC, datetime

from .gate import SignupGate

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "signup_gate"


class SupabaseSignupGateStore:
    """The production signup-gate store: Supabase Postgres via a lazy service-role client.

    Mirrors the other runtime Supabase stores — the service-role client bypasses RLS (the gate
    table is otherwise reachable only by the auth hook), built lazily on first use so construction
    needs no creds and no network. The synchronous supabase-py calls run off the event loop via
    ``asyncio.to_thread``. The table holds a single row (``id = true``); reads take it, writes
    upsert it. The invite code is a low-value shared secret stored as plaintext — RLS + revoked
    grants, not encryption, are the boundary (the admin must be able to read it back to hand out).
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach the gate"
                )
            self._client = create_client(url, key)
        return self._client

    async def get(self) -> SignupGate:
        client = self._ensure_client()
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("invite_code, enforced, updated_at")
                .eq("id", True)
                .limit(1)
                .execute()
            )
        )
        rows = response.data or []
        if not rows:
            # Fail open: a missing row ⇒ the gate is off (the hook fails open the same way), so a
            # seed/config slip can never lock everyone out of signup.
            return SignupGate(invite_code="", enforced=False)
        row = rows[0]
        return SignupGate(
            invite_code=str(row["invite_code"]),
            enforced=bool(row["enforced"]),
            updated_at=_parse_timestamp(row.get("updated_at")),
        )

    async def save(self, gate: SignupGate, *, updated_by: str | None = None) -> SignupGate:
        client = self._ensure_client()
        now = datetime.now(UTC)
        row = {
            "id": True,
            "invite_code": gate.invite_code,
            "enforced": gate.enforced,
            "updated_at": now.isoformat(),
            "updated_by": updated_by,
        }
        # Upsert on the singleton PK so a first write creates the row and later writes replace it.
        await asyncio.to_thread(
            lambda: client.table(_TABLE).upsert(row, on_conflict="id").execute()  # type: ignore[attr-defined]
        )
        return SignupGate(invite_code=gate.invite_code, enforced=gate.enforced, updated_at=now)


def _parse_timestamp(value: object) -> datetime | None:
    """Parse the ISO timestamp PostgREST returns; None/unparseable → None (display only)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
