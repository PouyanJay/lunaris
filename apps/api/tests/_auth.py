"""Shared HS256 auth helpers for the Phase-2 API tests (not collected — leading underscore).

Hermetic: mints the JWT Supabase Auth would issue, signed with the secret the API is configured
with in these tests, so the real auth path runs with no live Supabase. One source for the secret +
the two canonical test user ids, reused across the isolation / BYOK / config / variant suites.
"""

import time

import jwt

JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long-xxxx"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def mint_token(sub: str) -> str:
    """An HS256 token for ``sub`` with the audience/role Supabase Auth sets, valid for an hour."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def auth_headers(sub: str) -> dict[str, str]:
    """The ``Authorization: Bearer`` header for ``sub``."""
    return {"Authorization": f"Bearer {mint_token(sub)}"}
