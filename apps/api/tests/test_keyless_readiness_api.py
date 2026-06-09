"""T8 (keyless-fallbacks): GET /api/keyless/readiness — is the serverless GPU ready to serve?

The web polls this so a keyless build can show a "Provisioning GPU…" state instead of a silent wait
while the scale-to-zero GPU wakes. Tenant-aware: a caller whose LLM is keyed gets ``not_applicable``
(a hosted API, no GPU), and the endpoint never probes; a keyless caller gets the live probe result.
"""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import auth_headers as _auth
from _doubles import AcceptingValidator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import (
    get_credential_vault,
    get_secret_store,
    get_secret_validator,
)
from lunaris_api.routers import keyless as keyless_router
from lunaris_api.secrets import KNOWN_SECRETS, SecretStore
from lunaris_api.secrets.credential_store_protocol import CredentialStatus
from lunaris_runtime.resilience import ReadinessStatus


@pytest.fixture(autouse=True)
def _restore_secret_env() -> Iterator[None]:
    saved = {var: os.environ.get(var) for var in KNOWN_SECRETS.values()}
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


@pytest.fixture(autouse=True)
def _stub_probe(monkeypatch) -> Iterator[list[bool]]:
    """Replace the live HTTP probe by default so tests never touch the network; records whether it
    was called so a test can assert the keyed path skips it. Returns PROVISIONING by default."""
    called: list[bool] = []

    async def fake_probe(**_kwargs: object) -> ReadinessStatus:
        called.append(True)
        return ReadinessStatus.PROVISIONING

    monkeypatch.setattr(keyless_router, "probe_keyless_llm_endpoint", fake_probe)
    return called


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
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


async def test_keyless_caller_gets_the_live_probe_result(
    client: httpx.AsyncClient, _stub_probe: list[bool]
) -> None:
    body = (await client.get("/api/keyless/readiness")).json()

    assert body["status"] == "provisioning"
    assert _stub_probe == [True]  # the probe ran


async def test_a_keyed_caller_is_not_applicable_and_skips_the_probe(
    client: httpx.AsyncClient, _stub_probe: list[bool]
) -> None:
    # The caller set their Anthropic key → a hosted API, no GPU to provision.
    await client.put("/api/settings/secrets/anthropic", json={"value": "sk-ant-key-4242"})

    body = (await client.get("/api/keyless/readiness")).json()

    assert body["status"] == "not_applicable"
    assert _stub_probe == []  # the probe is skipped — no needless wake of a non-existent GPU


async def test_ready_probe_is_surfaced(client: httpx.AsyncClient, monkeypatch) -> None:
    async def ready_probe(**_kwargs: object) -> ReadinessStatus:
        return ReadinessStatus.READY

    monkeypatch.setattr(keyless_router, "probe_keyless_llm_endpoint", ready_probe)

    body = (await client.get("/api/keyless/readiness")).json()

    assert body["status"] == "ready"


# --- BYOK + auth variants ----------------------------------------------------------------------


class _FakeVault:
    def __init__(self, set_providers: set[str]) -> None:
        self._set = set_providers

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]:
        return [
            CredentialStatus(provider=p, is_set=p in self._set, last4=None)
            for p in ("anthropic", "voyage", "search", "youtube")
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


async def test_byok_keyed_tenant_is_not_applicable(tmp_path: Path, _stub_probe: list[bool]) -> None:
    vault = _FakeVault({"anthropic"})

    async with _byok_client(tmp_path, vault) as client:
        body = (await client.get("/api/keyless/readiness", headers=_auth(_USER_A))).json()

    assert body["status"] == "not_applicable"
    assert _stub_probe == []


async def test_byok_keyless_tenant_gets_the_probe(tmp_path: Path, _stub_probe: list[bool]) -> None:
    vault = _FakeVault(set())  # tenant set no keys → keyless → probe the GPU

    async with _byok_client(tmp_path, vault) as client:
        body = (await client.get("/api/keyless/readiness", headers=_auth(_USER_A))).json()

    assert body["status"] == "provisioning"
    assert _stub_probe == [True]


async def test_anonymous_caller_is_blocked_under_auth(tmp_path: Path) -> None:
    vault = _FakeVault(set())

    async with _byok_client(tmp_path, vault) as client:
        response = await client.get("/api/keyless/readiness")

    assert response.status_code == 401
