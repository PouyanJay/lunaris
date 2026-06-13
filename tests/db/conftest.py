"""Shared live-DB harness for the tests/db suites.

Every suite here is eval-marked and ``SUPABASE_DB_URL``-gated (each module declares its own
``pytestmark``); these fixtures assume that gate has already passed. The connection role is the
local ``postgres`` superuser, so Arrange-phase writes simulate the backend's service path
(bypassing RLS) until a test switches role via ``as_user``.
"""

import json
import os
from collections.abc import Callable, Iterator

import pytest

psycopg = pytest.importorskip("psycopg")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")


@pytest.fixture
def db() -> Iterator["psycopg.Cursor"]:
    """A cursor inside one never-committed transaction — every test leaves the DB untouched."""
    with psycopg.connect(SUPABASE_DB_URL) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            yield cur
        conn.rollback()


@pytest.fixture
def as_user() -> Callable[["psycopg.Cursor", str], None]:
    """Become an authenticated user for the rest of the transaction, the way PostgREST does."""

    def _switch(cur: "psycopg.Cursor", user_id: str) -> None:
        cur.execute("set local role authenticated")
        claims = json.dumps({"sub": user_id, "role": "authenticated"})
        cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))

    return _switch
