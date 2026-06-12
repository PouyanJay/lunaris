"""Phase 2 variant coverage (T9) — the auth boundary, run-scope isolation under concurrency, and
input edge cases, consolidated as the journey's final parametrized pass.

Covers what the per-task tests proved in isolation, as cross-cutting variants:
- every user-scoped route rejects an anonymous caller with 401 when auth is configured;
- two builds running CONCURRENTLY each use their own keys + model (the contextvar run-scope is
  copied per asyncio task, so nothing bleeds across tenants);
- config input bounds (oversized value) and credential rotation.

Hermetic (HS256 tokens, in-memory stores, stub/recording pipelines) — no live Supabase.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.service import CourseService
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.run_config import resolve_config


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config.json",
        supabase_jwt_secret=JWT_SECRET,  # auth ON
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


# --- the auth boundary: every user-scoped route rejects an anonymous caller ----------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("GET", "/api/runs"),
        ("GET", "/api/credentials"),
        ("GET", "/api/config"),
        ("GET", "/api/courses/deadbeef"),
        ("GET", "/api/courses/stream?topic=x"),  # the SSE build path
        ("GET", "/api/runs/somerun/events"),
        ("GET", "/api/runs/somerun/bridge/requests?wait=0"),  # the device-bridge work feed
        ("DELETE", "/api/courses/deadbeef"),
        ("POST", "/api/runs/somerun/cancel"),
        ("POST", "/api/runs/somerun/bridge/results"),  # the device-bridge answer path
        ("POST", "/api/courses"),
    ],
)
async def test_user_route_rejects_anonymous_when_auth_on(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, json={"topic": "x"})

    assert response.status_code == 401, f"{method} {path} → {response.status_code}"


async def test_a_valid_token_passes_the_boundary(client: httpx.AsyncClient) -> None:
    # The same route that 401s for anon returns the caller's id for a valid token (boundary, not a
    # blanket block).
    response = await client.get("/api/me", headers=auth_headers(USER_A))

    assert response.status_code == 200
    assert response.json()["userId"] == USER_A


# --- run-scope isolation under real concurrency --------------------------------------------------


class _BarrierPipeline:
    """Records the keys+model each concurrent run sees, after a barrier forces both to be in-flight
    simultaneously — so a cross-tenant context bleed would be observed if it existed."""

    def __init__(
        self, barrier: asyncio.Barrier, sink: dict[str, tuple[str | None, str | None]]
    ) -> None:
        self._barrier = barrier
        self._sink = sink

    async def run(self, topic: str, *, course_id: str, run_id: str, **_: object) -> None:
        await self._barrier.wait()  # both runs are now past this point at the same time
        self._sink[course_id] = (
            resolve_secret("ANTHROPIC_API_KEY"),
            resolve_config("LUNARIS_MODEL_STRONG"),
        )
        return None


async def test_concurrent_builds_use_their_own_keys_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a platform default in env; two tenants each with their own key + model.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "platform-model")
    sink: dict[str, tuple[str | None, str | None]] = {}
    barrier = asyncio.Barrier(2)

    async def cred_resolver(user_id: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": f"key-{user_id}"}

    async def cfg_resolver(user_id: str) -> dict[str, str]:
        return {"LUNARIS_MODEL_STRONG": f"model-{user_id}"}

    service = CourseService(
        CourseStore(tmp_path),
        lambda _store: _BarrierPipeline(barrier, sink),
        credential_resolver=cred_resolver,
        config_resolver=cfg_resolver,
    )

    # Act — two builds run concurrently, forced to overlap by the barrier.
    await asyncio.gather(
        service.create("a", course_id="ca", run_id="ra", owner_id=USER_A),
        service.create("b", course_id="cb", run_id="rb", owner_id=USER_B),
    )

    # Assert — each run saw ONLY its own tenant's key + model; no bleed across the concurrent tasks,
    # and the platform env defaults never leaked into either tenant build.
    assert sink["ca"] == (f"key-{USER_A}", f"model-{USER_A}")
    assert sink["cb"] == (f"key-{USER_B}", f"model-{USER_B}")
    assert "platform-key" not in {sink["ca"][0], sink["cb"][0]}


# --- input bounds + rotation ---------------------------------------------------------------------


async def test_oversized_config_value_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/config/modelStrong", json={"value": "x" * 201}, headers=auth_headers(USER_A)
    )

    assert response.status_code == 422


async def test_empty_config_value_is_rejected(client: httpx.AsyncClient) -> None:
    # A blank model id is meaningless; the service rejects it (422) rather than store an empty one.
    response = await client.put(
        "/api/config/modelStrong", json={"value": "   "}, headers=auth_headers(USER_A)
    )

    assert response.status_code == 422


async def test_config_value_can_be_rotated_in_place(client: httpx.AsyncClient) -> None:
    # Arrange / Act — set, then overwrite.
    headers = auth_headers(USER_A)
    await client.put("/api/config/modelStrong", json={"value": "first"}, headers=headers)
    await client.put("/api/config/modelStrong", json={"value": "second"}, headers=headers)
    get = await client.get("/api/config", headers=headers)

    # Assert — the latest value wins (one row per key per user).
    settings = {s["name"]: s["value"] for s in get.json()["settings"]}
    assert settings["modelStrong"] == "second"
