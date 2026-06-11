"""Keyless explain (local-intelligence Phase 1, T1): the reader's "Lunaris server" compute option.

The explain capability widens from key-gated to tiered: a keyed caller (env or their own vault key)
gets Claude (``source: hosted``); an unkeyed caller gets the keyless server model
(``source: server-fallback``) behind a small per-user daily cap; with the Draft tier disabled the
keyless path stays a clean 503. Anonymous callers are 401 when auth is configured — explains spend
server compute.
"""

from collections.abc import AsyncIterator
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
from lunaris_api.credential_vault import CredentialVault
from lunaris_api.dependencies import (
    get_explain_binding,
    get_explain_throttle,
    get_secret_store,
)
from lunaris_api.explain import ExplainBinding, IExplainer
from lunaris_api.explain_throttle import KeylessExplainThrottle
from lunaris_api.secrets import InMemoryCredentialStore, SecretCipher, SecretStore


class _StubExplainer(IExplainer):
    """Returns a fixed explanation — no model, no key."""

    async def explain(self, content: str, context: str | None) -> str:
        return "Plain words."


def _binding(source: str) -> ExplainBinding:
    return ExplainBinding(explainer=_StubExplainer(), source=source, credentials=None)


def _build_client(
    tmp_path: Path,
    *,
    binding: ExplainBinding | None,
    throttle: KeylessExplainThrottle | None = None,
    jwt_secret: str | None = None,
) -> httpx.AsyncClient:
    app = create_app()
    env_file = tmp_path / ".env"
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=env_file,
        supabase_jwt_secret=jwt_secret,
    )
    app.dependency_overrides[get_secret_store] = lambda: SecretStore(env_file)
    app.dependency_overrides[get_explain_binding] = lambda: binding
    if throttle is not None:
        app.dependency_overrides[get_explain_throttle] = lambda: throttle
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def keyless_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, binding=_binding("server-fallback")) as client:
        yield client


async def test_keyless_explain_answers_with_server_fallback_provenance(
    keyless_client: httpx.AsyncClient,
) -> None:
    # Arrange — the keyless_client fixture binds a server-fallback stub explainer.

    # Act
    response = await keyless_client.post("/api/explain", json={"content": "{}"})

    # Assert — answered, and the wire says WHICH tier answered (the badge's source of truth).
    assert response.status_code == 200
    assert response.json() == {"explanation": "Plain words.", "source": "server-fallback"}


async def test_keyed_explain_carries_hosted_provenance(tmp_path: Path) -> None:
    # Arrange
    async with _build_client(tmp_path, binding=_binding("hosted")) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert
    assert response.status_code == 200
    assert response.json()["source"] == "hosted"


async def test_keyless_explain_is_capped_per_day(tmp_path: Path) -> None:
    # Arrange — a real throttle with a cap of 1 (the second call must be refused).
    throttle = KeylessExplainThrottle(daily_cap=1)
    async with _build_client(
        tmp_path, binding=_binding("server-fallback"), throttle=throttle
    ) as client:
        # Act
        first = await client.post("/api/explain", json={"content": "{}"})
        second = await client.post("/api/explain", json={"content": "{}"})

    # Assert — the cap refuses with a recoverable 429 and a human detail.
    assert first.status_code == 200
    assert second.status_code == 429
    assert "today" in second.json()["detail"].lower()


async def test_explain_cap_is_per_user(tmp_path: Path) -> None:
    # Arrange — auth on; A exhausts the cap, B must be unaffected.
    throttle = KeylessExplainThrottle(daily_cap=1)
    async with _build_client(
        tmp_path,
        binding=_binding("server-fallback"),
        throttle=throttle,
        jwt_secret=_JWT_SECRET,
    ) as client:
        # Act
        a_first = await client.post("/api/explain", json={"content": "{}"}, headers=_auth(_USER_A))
        a_second = await client.post("/api/explain", json={"content": "{}"}, headers=_auth(_USER_A))
        b_first = await client.post("/api/explain", json={"content": "{}"}, headers=_auth(_USER_B))

    # Assert
    assert a_first.status_code == 200
    assert a_second.status_code == 429
    assert b_first.status_code == 200


async def test_hosted_explain_is_never_capped(tmp_path: Path) -> None:
    # Arrange — a zero-cap throttle; the keyed (hosted) path must not consult it.
    throttle = KeylessExplainThrottle(daily_cap=0)
    async with _build_client(tmp_path, binding=_binding("hosted"), throttle=throttle) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert
    assert response.status_code == 200


async def test_anonymous_explain_is_rejected_when_auth_is_configured(tmp_path: Path) -> None:
    # Arrange — auth on, no Authorization header.
    async with _build_client(
        tmp_path, binding=_binding("server-fallback"), jwt_secret=_JWT_SECRET
    ) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert — explain spends server compute; anonymous is rejected like every user surface.
    assert response.status_code == 401


class _NeverExplainer(IExplainer):
    async def explain(self, content: str, context: str | None) -> str:  # pragma: no cover
        raise AssertionError("the throttle must refuse before the model is called")


async def test_cap_refusal_never_reaches_the_model(tmp_path: Path) -> None:
    # Arrange — cap 0: every keyless call is refused; the explainer must never run.
    throttle = KeylessExplainThrottle(daily_cap=0)
    binding = ExplainBinding(
        explainer=_NeverExplainer(), source="server-fallback", credentials=None
    )
    async with _build_client(tmp_path, binding=binding, throttle=throttle) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert
    assert response.status_code == 429


# ── binding resolution (the dependency itself, no HTTP / no model call) ─────────────────────────


def _settings(tmp_path: Path, *, draft: bool) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        draft_tier_enabled=draft,
    )


async def test_env_keyed_caller_resolves_to_hosted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")

    # Act
    binding = await get_explain_binding(
        owner_id=None, vault=None, settings=_settings(tmp_path, draft=True)
    )

    # Assert
    assert binding is not None and binding.source == "hosted"


async def test_unkeyed_caller_resolves_to_server_fallback_when_draft_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Act
    binding = await get_explain_binding(
        owner_id=None, vault=None, settings=_settings(tmp_path, draft=True)
    )

    # Assert
    assert binding is not None and binding.source == "server-fallback"


async def test_unkeyed_caller_with_draft_disabled_has_no_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Act / Assert — today's fail-closed 503 survives when the keyless tier is off.
    assert (
        await get_explain_binding(
            owner_id=None, vault=None, settings=_settings(tmp_path, draft=False)
        )
        is None
    )


async def test_vault_keyed_caller_resolves_to_hosted_with_their_own_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — no platform key; the caller's own Anthropic key is in the vault (real cipher).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    vault = CredentialVault(
        store=InMemoryCredentialStore(),
        cipher=SecretCipher(b"\x07" * 32),
        validator=AcceptingValidator(),
    )
    await vault.set(user_id=_USER_A, provider="anthropic", value="sk-ant-tenant-own")

    # Act
    binding = await get_explain_binding(
        owner_id=_USER_A, vault=vault, settings=_settings(tmp_path, draft=True)
    )

    # Assert — hosted, on the tenant's own key (carried as the run scope, never the env).
    assert binding is not None and binding.source == "hosted"
    assert binding.credentials is not None
    assert binding.credentials.get("ANTHROPIC_API_KEY") == "sk-ant-tenant-own"


async def test_vault_unkeyed_caller_resolves_to_server_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — auth + vault, but this caller stored no Anthropic key. A PLATFORM env key may
    # exist; the tenant scope must still exclude it (tenant-only, no env fallback in scope).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")
    vault = CredentialVault(
        store=InMemoryCredentialStore(),
        cipher=SecretCipher(b"\x07" * 32),
        validator=AcceptingValidator(),
    )

    # Act
    binding = await get_explain_binding(
        owner_id=_USER_A, vault=vault, settings=_settings(tmp_path, draft=True)
    )

    # Assert — the tenant runs keyless (their choice to add a key), never on the platform key.
    assert binding is not None and binding.source == "server-fallback"
    assert binding.credentials is not None
    assert "ANTHROPIC_API_KEY" not in binding.credentials


@pytest.mark.parametrize("source", ["hosted", "server-fallback"])
async def test_every_server_tier_reports_its_provenance(tmp_path: Path, source: str) -> None:
    # Arrange — the same route must stamp whichever tier answered (variant coverage).
    async with _build_client(tmp_path, binding=_binding(source)) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert
    assert response.status_code == 200
    assert response.json()["source"] == source
