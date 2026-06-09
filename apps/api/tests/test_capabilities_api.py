"""Capability status: GET /api/settings reports, per capability, whether the live provider's key is
set (mode=live) or it's running on its keyless fallback (mode=fallback). This is the live badge the
web shows; it flips to live the moment the real key is stored."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from _doubles import AcceptingValidator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_secret_store, get_secret_validator
from lunaris_api.secrets import KNOWN_SECRETS, SecretStore


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


async def test_capabilities_are_fallback_when_no_keys_are_set(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/capabilities")).json()

    caps = {c["capability"]: c for c in body}
    assert caps["llm"]["mode"] == "fallback"
    assert caps["embeddings"]["mode"] == "fallback"
    assert caps["search"]["mode"] == "fallback"
    assert caps["video"]["mode"] == "fallback"
    # The fallback provider is named so the UI can say which one is in effect.
    assert caps["llm"]["provider"] == "Bonsai 8B (1-bit, local)"
    assert caps["search"]["provider"] == "DuckDuckGo"


async def test_capability_flips_to_live_when_its_key_is_set(client: httpx.AsyncClient) -> None:
    await client.put("/api/settings/secrets/anthropic", json={"value": "sk-ant-live-key-4242"})

    body = (await client.get("/api/capabilities")).json()

    caps = {c["capability"]: c for c in body}
    assert caps["llm"]["mode"] == "live"
    assert caps["llm"]["provider"] == "Anthropic Claude"
    # The others stay on their fallbacks — the badge is per-capability, not all-or-nothing.
    assert caps["embeddings"]["mode"] == "fallback"
