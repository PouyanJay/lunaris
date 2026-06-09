"""T7 (keyless-fallbacks): variant coverage for the live capability badge.

Parametrizes the key-present/absent matrix across every capability and covers both presence sources
the badge reads: the operator file store (single-user, auth off) and — the piece deferred from T4 —
the per-tenant BYOK vault, where the badge reflects the *caller's own* keys. Under configured auth
the badge is per-tenant, so an anonymous caller is blocked (401) rather than served a shared view.
"""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import USER_B as _USER_B
from _auth import auth_headers as _auth
from _doubles import AcceptingValidator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import (
    get_credential_vault,
    get_secret_store,
    get_secret_validator,
)
from lunaris_api.secrets import KNOWN_SECRETS, SecretStore
from lunaris_api.secrets.credential_store_protocol import CredentialStatus


async def _caps(client: httpx.AsyncClient, **kwargs: object) -> dict[str, dict]:
    """The capability badge as a ``{capability: row}`` map, for terse per-capability assertions."""
    response = await client.get("/api/capabilities", **kwargs)
    return {row["capability"]: row for row in response.json()}


@pytest.fixture(autouse=True)
def _restore_secret_env() -> Iterator[None]:
    saved = {var: os.environ.get(var) for var in KNOWN_SECRETS.values()}
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    # File-store path (no BYOK): the live badge reads the operator secret store.
    app = create_app()
    env_file = tmp_path / ".env"
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=env_file
    )
    app.dependency_overrides[get_secret_store] = lambda: SecretStore(env_file)
    app.dependency_overrides[get_secret_validator] = lambda: AcceptingValidator()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


# (secret id the UI PUTs, capability it powers, the live provider label) for each capability.
_CAPABILITY_MATRIX = [
    ("anthropic", "llm", "Anthropic Claude"),
    ("voyage", "embeddings", "Voyage"),
    ("search", "search", "Tavily"),
    ("youtube", "video", "YouTube"),
]


@pytest.mark.parametrize(("secret_id", "capability", "live_label"), _CAPABILITY_MATRIX)
async def test_setting_one_key_flips_only_its_capability_to_live(
    client: httpx.AsyncClient, secret_id: str, capability: str, live_label: str
) -> None:
    # Arrange / Act — set exactly one provider's key.
    await client.put(f"/api/settings/secrets/{secret_id}", json={"value": "a-real-key-value-4242"})
    caps = await _caps(client)

    # Assert — that capability is live with its real provider; every other stays on its fallback.
    assert caps[capability]["mode"] == "live"
    assert caps[capability]["provider"] == live_label
    others = [name for (_, name, _) in _CAPABILITY_MATRIX if name != capability]
    assert all(caps[name]["mode"] == "fallback" for name in others)


async def test_all_capabilities_live_when_every_key_is_set(client: httpx.AsyncClient) -> None:
    for secret_id, _capability, _label in _CAPABILITY_MATRIX:
        await client.put(f"/api/settings/secrets/{secret_id}", json={"value": "key-value-4242"})

    caps = await _caps(client)

    assert all(caps[name]["mode"] == "live" for (_, name, _) in _CAPABILITY_MATRIX)


# --- BYOK-aware capabilities (the test deferred from T4) ---------------------------------------


class _FakeVault:
    """A credential vault stub returning each user's set providers, so the badge is BYOK-aware."""

    def __init__(self, set_by_user: dict[str, set[str]]) -> None:
        self._set_by_user = set_by_user

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]:
        owned = self._set_by_user.get(user_id, set())
        return [
            CredentialStatus(provider=provider, is_set=provider in owned, last4=None)
            for provider in ("anthropic", "voyage", "search", "youtube")
        ]


@asynccontextmanager
async def _byok_client(tmp_path: Path, vault: _FakeVault) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=_JWT_SECRET,
    )
    app.dependency_overrides[get_credential_vault] = lambda: vault
    app.dependency_overrides[get_secret_store] = lambda: SecretStore(tmp_path / ".env")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_byok_badge_reflects_the_authenticated_callers_own_keys(tmp_path: Path) -> None:
    # User A set their Anthropic key; user B set nothing. With BYOK on, each caller's badge reflects
    # their OWN vault — not a process-wide store.
    vault = _FakeVault({_USER_A: {"anthropic"}})

    async with _byok_client(tmp_path, vault) as client:
        caps_a = await _caps(client, headers=_auth(_USER_A))
        caps_b = await _caps(client, headers=_auth(_USER_B))

    assert caps_a["llm"]["mode"] == "live"  # A's own Anthropic key
    assert caps_b["llm"]["mode"] == "fallback"  # B set nothing → keyless for B


async def test_anonymous_caller_is_blocked_under_configured_auth(tmp_path: Path) -> None:
    # With auth configured (BYOK), the capability badge is per-tenant, so an unauthenticated caller
    # is rejected (401) rather than served a process-wide view — anon stays blocked.
    vault = _FakeVault({_USER_A: {"anthropic"}})

    async with _byok_client(tmp_path, vault) as client:
        response = await client.get("/api/capabilities")

    assert response.status_code == 401


async def test_file_store_badge_when_auth_is_off(client: httpx.AsyncClient) -> None:
    # Auth OFF (the single-user/admin deployment, the `client` fixture): no token needed, and the
    # badge reads the operator file store — here empty, so every capability is on its fallback.
    caps = await _caps(client)

    assert all(caps[name]["mode"] == "fallback" for (_, name, _) in _CAPABILITY_MATRIX)
