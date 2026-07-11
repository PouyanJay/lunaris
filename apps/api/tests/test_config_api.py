"""Config API: non-secret runtime settings — values ARE shown (unlike secrets), with defaults."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.config_store import KNOWN_CONFIG, ConfigStore
from lunaris_api.dependencies import get_config_store
from lunaris_runtime.schema import VideoKind
from lunaris_runtime.video_build import target_seconds_for


@pytest.fixture(autouse=True)
def _restore_config_env() -> Iterator[None]:
    saved = {var: os.environ.get(var) for var in KNOWN_CONFIG.values()}
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def _client(tmp_path: Path) -> httpx.AsyncClient:
    app = create_app()
    config_file = tmp_path / "config.json"
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=config_file,
    )
    app.dependency_overrides[get_config_store] = lambda: ConfigStore(config_file)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(tmp_path) as http_client:
        yield http_client


async def test_get_returns_every_setting_with_its_default(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/config")
    assert response.status_code == 200
    body = response.json()

    settings = {s["name"]: s for s in body["settings"]}
    assert set(settings) == {
        "langsmithTracing",
        "langsmithProject",
        "modelStrong",
        "modelWorker",
        "videoEnabled",
        "videoLessonsEnabled",
        "videoVoice",
        "videoSummarySeconds",
        "videoOverviewSeconds",
        "videoLessonSeconds",
        "coverGenerationEnabled",
        "coverStylePreset",
    }
    # Unset → the value IS the default, and the default is reported alongside it.
    assert settings["langsmithTracing"] == {
        "name": "langsmithTracing",
        "value": "false",
        "default": "false",
        "kind": "toggle",
        "restartRequired": True,
    }
    # The cover preset default is GENERAL (cover-general-preset). Regression: the config-store
    # default once stayed 'nocturne' when every other layer flipped, so the Settings dropdown
    # showed Nocturne selected beside a General option labeled "(default)" — and a no-op save
    # would persist the wrong preset.
    assert settings["coverStylePreset"]["value"] == "general"
    assert settings["coverStylePreset"]["default"] == "general"
    assert settings["modelStrong"]["value"] == "claude-opus-4-8"
    assert settings["modelWorker"]["kind"] == "model"
    assert settings["modelWorker"]["restartRequired"] is False
    # The V6 video settings: master + voice default ON (toggle, no restart), lengths are bounded
    # numbers defaulting to the per-kind product lengths.
    assert settings["videoEnabled"] == {
        "name": "videoEnabled",
        "value": "true",
        "default": "true",
        "kind": "toggle",
        "restartRequired": False,
    }
    assert settings["videoVoice"]["value"] == "true"
    # The per-lesson sub-toggle: a toggle defaulting ON (so an unset value keeps every lesson's
    # video), no restart needed — read per build like the master toggle.
    assert settings["videoLessonsEnabled"] == {
        "name": "videoLessonsEnabled",
        "value": "true",
        "default": "true",
        "kind": "toggle",
        "restartRequired": False,
    }
    assert settings["videoLessonSeconds"]["kind"] == "number"
    # Lengths default to the per-kind product lengths (no drift if the defaults change).
    assert settings["videoLessonSeconds"]["value"] == str(target_seconds_for(VideoKind.LESSON))
    assert settings["videoOverviewSeconds"]["value"] == str(target_seconds_for(VideoKind.OVERVIEW))


async def test_put_updates_the_value_and_the_environment(client: httpx.AsyncClient) -> None:
    updated = (
        await client.put("/api/config/modelWorker", json={"value": "claude-sonnet-4-6"})
    ).json()

    assert updated["value"] == "claude-sonnet-4-6"
    # Applied to os.environ so the next build's composition reads it.
    assert os.environ["LUNARIS_MODEL_WORKER"] == "claude-sonnet-4-6"
    # And it is reflected on a subsequent GET.
    body = (await client.get("/api/config")).json()
    assert next(s for s in body["settings"] if s["name"] == "modelWorker")["value"] == (
        "claude-sonnet-4-6"
    )


async def test_toggle_accepts_true_false_and_rejects_other(client: httpx.AsyncClient) -> None:
    ok = await client.put("/api/config/langsmithTracing", json={"value": "true"})
    assert ok.status_code == 200
    assert ok.json()["value"] == "true"

    bad = await client.put("/api/config/langsmithTracing", json={"value": "yes"})
    assert bad.status_code == 422


async def test_empty_text_value_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/config/langsmithProject", json={"value": "  "})
    assert response.status_code == 422


async def test_video_length_in_bounds_is_accepted_and_applied_to_env(
    client: httpx.AsyncClient,
) -> None:
    # Arrange / Act — an in-bounds whole-second value.
    ok = await client.put("/api/config/videoLessonSeconds", json={"value": "90"})

    # Assert — accepted and applied to the env the next build's run-config scope reads.
    assert ok.status_code == 200
    assert ok.json()["value"] == "90"
    assert os.environ["LUNARIS_VIDEO_LESSON_SECONDS"] == "90"


async def test_video_length_out_of_range_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/config/videoLessonSeconds", json={"value": "100000"})
    assert response.status_code == 422


async def test_video_length_non_numeric_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/config/videoLessonSeconds", json={"value": "soon"})
    assert response.status_code == 422


async def test_video_master_toggle_persists(client: httpx.AsyncClient) -> None:
    off = await client.put("/api/config/videoEnabled", json={"value": "false"})
    assert off.status_code == 200
    assert off.json()["value"] == "false"
    body = (await client.get("/api/config")).json()
    assert next(s for s in body["settings"] if s["name"] == "videoEnabled")["value"] == "false"


async def test_video_lessons_toggle_persists(client: httpx.AsyncClient) -> None:
    # The per-lesson sub-toggle round-trips like the master toggle, and applies to the env the next
    # build's run-config scope reads (so the gate sees it).
    off = await client.put("/api/config/videoLessonsEnabled", json={"value": "false"})
    assert off.status_code == 200
    assert off.json()["value"] == "false"
    assert os.environ["LUNARIS_VIDEO_LESSONS_ENABLED"] == "false"
    body = (await client.get("/api/config")).json()
    assert next(s for s in body["settings"] if s["name"] == "videoLessonsEnabled")["value"] == (
        "false"
    )


async def test_unknown_key_is_404(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/config/nope", json={"value": "x"})
    assert response.status_code == 404


async def test_persisted_value_survives_a_reload(tmp_path: Path) -> None:
    # A second store on the same file sees the write — proving on-disk persistence across restarts.
    config_file = tmp_path / "config.json"
    ConfigStore(config_file).set("langsmithProject", "my-project")
    reloaded_store = ConfigStore(config_file)
    reloaded = {s.name: s.value for s in reloaded_store.settings()}
    assert reloaded["langsmithProject"] == "my-project"
    # The reload also re-hydrates os.environ (so the langsmith SDK sees it at the next startup).
    assert os.environ["LANGSMITH_PROJECT"] == "my-project"
