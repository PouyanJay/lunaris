import asyncio
import os
from datetime import datetime

from supabase_auth.errors import AuthApiError

from .account import AdminAccount

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
# GoTrue paginates list_users; fetch a wide page so a pilot's accounts come back in one round-trip,
# and follow further pages so the list is never silently truncated. The cap is a runaway guard.
_PAGE_SIZE = 200
_MAX_PAGES = 50


class SupabaseUserDirectory:
    """Lists/deletes Supabase Auth users via the service-role GoTrue admin API.

    Mirrors the other runtime Supabase clients: a lazy service-role client (built from the
    environment on first use, so construction needs no creds/network), and the synchronous
    supabase-py admin calls run off the event loop via ``asyncio.to_thread``. The service-role key
    is required — the GoTrue admin API (list/delete users) is privileged and never reachable with
    an end-user token.
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
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot list users"
                )
            self._client = create_client(url, key)
        return self._client

    async def list_accounts(self) -> list[AdminAccount]:
        client = self._ensure_client()
        accounts: list[AdminAccount] = []
        for page in range(1, _MAX_PAGES + 1):
            result = await asyncio.to_thread(
                lambda p=page: client.auth.admin.list_users(page=p, per_page=_PAGE_SIZE)  # type: ignore[attr-defined]
            )
            # list_users() returns a plain list[User]; the getattr guards a differing supabase-py
            # version that might wrap it as ``.users``.
            users = getattr(result, "users", result)
            accounts.extend(_to_account(user) for user in users)
            if len(users) < _PAGE_SIZE:
                break
        return accounts

    async def delete_account(self, user_id: str) -> None:
        client = self._ensure_client()
        try:
            await asyncio.to_thread(lambda: client.auth.admin.delete_user(user_id))  # type: ignore[attr-defined]
        except AuthApiError as exc:
            # Idempotent (per the protocol): an already-gone account — e.g. two admins deleting the
            # same row, or a retry — is not an error.
            if exc.status == 404:
                return
            raise


def _to_account(user: object) -> AdminAccount:
    return AdminAccount(
        id=str(getattr(user, "id", "")),
        email=getattr(user, "email", None),
        created_at=_as_datetime(getattr(user, "created_at", None)),
        last_sign_in_at=_as_datetime(getattr(user, "last_sign_in_at", None)),
        email_confirmed=getattr(user, "email_confirmed_at", None) is not None,
    )


def _as_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value if isinstance(value, datetime) else None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
