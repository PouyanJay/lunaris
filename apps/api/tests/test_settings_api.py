"""Settings API: secrets are write-only over HTTP — set with validation, never echoed back."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import (
    get_secret_store,
    get_secret_validator,
    pipeline_supports_lesson_regeneration,
)
from lunaris_api.secrets import KNOWN_SECRETS, SecretStore, SecretValidationError


class _RejectingValidator:
    async def validate(self, name: str, value: str) -> None:
        raise SecretValidationError("Anthropic rejected this API key.")


class _AcceptingValidator:
    async def validate(self, name: str, value: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _restore_secret_env() -> Iterator[None]:
    saved = {var: os.environ.get(var) for var in KNOWN_SECRETS.values()}
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def _client(tmp_path: Path, validator: object) -> httpx.AsyncClient:
    app = create_app()
    env_file = tmp_path / ".env"
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=env_file
    )
    app.dependency_overrides[get_secret_store] = lambda: SecretStore(env_file)
    app.dependency_overrides[get_secret_validator] = lambda: validator
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(tmp_path, _AcceptingValidator()) as http_client:
        yield http_client


async def test_settings_start_all_unset(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/settings")).json()

    names = {s["name"]: s for s in body["secrets"]}
    assert names["anthropic"]["isSet"] is False
    assert names["anthropic"]["last4"] is None
    assert body["pipeline"] == "stub"


async def test_settings_exposes_lesson_regeneration_capability(client: httpx.AsyncClient) -> None:
    # The reader hides the "Regenerate lesson" action when the active pipeline can't honour it
    # (returns 501) rather than offering a button that always fails. The stub pipeline is the
    # single-shot Orchestrator, which regenerates, so the flag is True here.
    body = (await client.get("/api/settings")).json()

    assert body["supportsLessonRegeneration"] is True


@pytest.mark.parametrize(
    ("pipeline", "supported"),
    [("stub", True), ("live", True), ("agent", False), ("bogus", False)],
)
def test_regeneration_capability_tracks_the_pipeline(pipeline: str, supported: bool) -> None:
    # Derived from each factory's declared return type, so it can never drift from the
    # isinstance(pipeline, LessonRegenerator) gate in CourseService.regenerate_lesson: the
    # single-shot Orchestrator (stub/live) regenerates; the deep agent and an unknown pipeline
    # do not.
    assert pipeline_supports_lesson_regeneration(pipeline) is supported


async def test_set_secret_is_write_only_and_never_echoes_the_value(
    client: httpx.AsyncClient,
) -> None:
    secret = "sk-ant-supersecret-value-4242"

    # Act — store it.
    put = await client.put("/api/settings/secrets/anthropic", json={"value": secret})

    # Assert — response reveals only set + last4, NEVER the value.
    assert put.status_code == 200
    assert put.json() == {"name": "anthropic", "isSet": True, "last4": "4242"}
    assert secret not in put.text

    # And a subsequent GET shows it set, still without the value anywhere in the payload.
    got = await client.get("/api/settings")
    assert secret not in got.text
    anthropic = next(s for s in got.json()["secrets"] if s["name"] == "anthropic")
    assert anthropic["isSet"] is True
    assert anthropic["last4"] == "4242"


async def test_invalid_key_is_rejected_and_not_stored(tmp_path: Path) -> None:
    async with _client(tmp_path, _RejectingValidator()) as client:
        put = await client.put(
            "/api/settings/secrets/anthropic", json={"value": "sk-ant-bogus-0000"}
        )
        assert put.status_code == 400
        assert "rejected" in put.json()["detail"].lower()

        got = await client.get("/api/settings")
        anthropic = next(s for s in got.json()["secrets"] if s["name"] == "anthropic")
        assert anthropic["isSet"] is False  # validation failure → not stored


async def test_unknown_secret_name_is_404(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/settings/secrets/bogus", json={"value": "x"})

    assert response.status_code == 404


async def test_control_characters_are_rejected_at_the_boundary(client: httpx.AsyncClient) -> None:
    # A newline could inject extra lines into the .env file the secret persists to; the router
    # rejects it with a deliberate 400 (not a Pydantic 422, which would echo the value back).
    injected = "sk-ant-good\nSEARCH_API_KEY=evil"

    put = await client.put("/api/settings/secrets/anthropic", json={"value": injected})

    assert put.status_code == 400
    assert injected not in put.text  # no part of the value is echoed back, even on rejection
    assert "sk-ant-good" not in put.text
    assert "evil" not in put.text
    got = await client.get("/api/settings")
    anthropic = next(s for s in got.json()["secrets"] if s["name"] == "anthropic")
    assert anthropic["isSet"] is False


async def test_empty_value_is_rejected(client: httpx.AsyncClient) -> None:
    # An empty value must not silently persist an empty .env line / blank env var.
    put = await client.put("/api/settings/secrets/search", json={"value": ""})

    assert put.status_code == 400
    got = await client.get("/api/settings")
    search = next(s for s in got.json()["secrets"] if s["name"] == "search")
    assert search["isSet"] is False


async def test_delete_clears_a_secret(client: httpx.AsyncClient) -> None:
    await client.put("/api/settings/secrets/voyage", json={"value": "pa-embed-1234"})

    cleared = await client.delete("/api/settings/secrets/voyage")

    assert cleared.status_code == 200
    assert cleared.json()["isSet"] is False
