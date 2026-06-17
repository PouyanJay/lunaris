"""Integration tests for per-user runtime config (Phase 2, T8).

With auth on, ``/api/config`` serves the caller's OWN model selection (from the per-user store, not
the process env); LangSmith is operator-only and absent. With auth off it falls back to the file
store (single-user dev). A build runs on the tenant's chosen model via the run-config scope.
"""

from pathlib import Path

import httpx
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import USER_B as _USER_B
from _auth import auth_headers as _auth
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import _runtime_config_resolver, get_user_config_store
from lunaris_api.service import CourseService
from lunaris_api.user_config import InMemoryUserConfigStore
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.run_config import resolve_config


def _client(tmp_path: Path, *, jwt_secret: str | None) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    store = InMemoryUserConfigStore()
    app.dependency_overrides[get_user_config_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config.json",
        supabase_jwt_secret=jwt_secret,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_authed_get_returns_only_the_per_user_settings(tmp_path: Path) -> None:
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        response = await client.get("/api/config", headers=_auth(_USER_A))

    assert response.status_code == 200, response.text
    names = {s["name"] for s in response.json()["settings"]}
    # Model selection + the V6 video settings; LangSmith is operator-only and absent here.
    assert names == {
        "modelStrong",
        "modelWorker",
        "videoEnabled",
        "videoLessonsEnabled",
        "videoVoice",
        "videoSummarySeconds",
        "videoOverviewSeconds",
        "videoLessonSeconds",
    }


async def test_authed_put_then_get_round_trips_video_config_per_user(tmp_path: Path) -> None:
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        put = await client.put(
            "/api/config/videoLessonSeconds", json={"value": "90"}, headers=_auth(_USER_A)
        )
        get = await client.get("/api/config", headers=_auth(_USER_A))

    assert put.status_code == 200, put.text
    settings = {s["name"]: s["value"] for s in get.json()["settings"]}
    assert settings["videoLessonSeconds"] == "90"


async def test_authed_put_then_get_round_trips_per_user(tmp_path: Path) -> None:
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        put = await client.put(
            "/api/config/modelStrong",
            json={"value": "claude-custom"},
            headers=_auth(_USER_A),
        )
        get = await client.get("/api/config", headers=_auth(_USER_A))

    assert put.status_code == 200, put.text
    settings = {s["name"]: s["value"] for s in get.json()["settings"]}
    assert settings["modelStrong"] == "claude-custom"


async def test_config_is_isolated_per_user(tmp_path: Path) -> None:
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        await client.put(
            "/api/config/modelStrong", json={"value": "a-model"}, headers=_auth(_USER_A)
        )
        b_get = await client.get("/api/config", headers=_auth(_USER_B))

    b_settings = {s["name"]: s for s in b_get.json()["settings"]}
    # User B never set it → sees the default (which implies it's not A's value).
    assert b_settings["modelStrong"]["value"] == b_settings["modelStrong"]["default"]


async def test_authed_put_operator_only_key_is_404(tmp_path: Path) -> None:
    # langsmithTracing is operator-only; the per-user surface rejects it.
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        response = await client.put(
            "/api/config/langsmithTracing", json={"value": "true"}, headers=_auth(_USER_A)
        )

    assert response.status_code == 404


async def test_anonymous_is_401_when_auth_on(tmp_path: Path) -> None:
    async with _client(tmp_path, jwt_secret=_JWT_SECRET) as client:
        response = await client.get("/api/config")

    assert response.status_code == 401


async def test_auth_off_uses_the_file_store_with_langsmith(tmp_path: Path) -> None:
    # With no JWT secret configured, config is the process-wide file store — all four keys, no auth.
    async with _client(tmp_path, jwt_secret=None) as client:
        response = await client.get("/api/config")

    assert response.status_code == 200, response.text
    names = {s["name"] for s in response.json()["settings"]}
    assert "langsmithTracing" in names and "modelStrong" in names


# --- the build uses the tenant's chosen model (run-config injection) -----------------------------


class _ModelRecordingPipeline:
    def __init__(self, sink: dict[str, str | None]) -> None:
        self._sink = sink

    async def run(self, topic: str, *, course_id: str, run_id: str, **_: object) -> None:
        self._sink["strong"] = resolve_config("LUNARIS_MODEL_STRONG")
        self._sink["worker"] = resolve_config("LUNARIS_MODEL_WORKER")
        return None


async def test_build_runs_on_the_tenants_chosen_model(tmp_path: Path, monkeypatch) -> None:
    # Arrange — the operator env has a default; the tenant chose a different strong model. The build
    # uses the REAL resolver over the per-user store, so this exercises the production mapping.
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "operator-strong")
    monkeypatch.delenv("LUNARIS_MODEL_WORKER", raising=False)
    store = InMemoryUserConfigStore()
    await store.set(user_id=_USER_A, key="modelStrong", value="tenant-strong")
    sink: dict[str, str | None] = {}
    service = CourseService(
        _file_store(tmp_path),
        lambda _store: _ModelRecordingPipeline(sink),
        config_resolver=_runtime_config_resolver(store),
    )

    # Act
    await service.create("topic", course_id="c1", run_id="r1", owner_id=_USER_A)

    # Assert — the build saw the tenant's strong model; the unset worker falls back to env (None).
    assert sink["strong"] == "tenant-strong"
    assert sink["worker"] is None


def _file_store(tmp_path: Path) -> object:
    from lunaris_runtime.persistence import CourseStore

    return CourseStore(tmp_path)
