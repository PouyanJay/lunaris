"""Per-user config store + service (Phase 2, T8).

The store holds each tenant's non-secret model selection, scoped by user_id; the service pairs a
stored value with its default/kind metadata and rejects keys outside the per-user surface.
"""

import pytest
from lunaris_api.config_store import ConfigError, ConfigKeyError
from lunaris_api.user_config import InMemoryUserConfigStore, UserConfigService

_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


async def test_store_set_then_get_all_round_trips() -> None:
    store = InMemoryUserConfigStore()

    await store.set(user_id=_USER_A, key="modelStrong", value="claude-opus-4-8")

    assert await store.get_all(user_id=_USER_A) == {"modelStrong": "claude-opus-4-8"}


async def test_store_is_scoped_per_user() -> None:
    # Arrange — two users set the same key to different values.
    store = InMemoryUserConfigStore()
    await store.set(user_id=_USER_A, key="modelWorker", value="worker-a")
    await store.set(user_id=_USER_B, key="modelWorker", value="worker-b")

    # Act / Assert — each reads only its own value.
    assert await store.get_all(user_id=_USER_A) == {"modelWorker": "worker-a"}
    assert await store.get_all(user_id=_USER_B) == {"modelWorker": "worker-b"}


async def test_store_set_overwrites_in_place() -> None:
    store = InMemoryUserConfigStore()
    await store.set(user_id=_USER_A, key="modelStrong", value="first")
    await store.set(user_id=_USER_A, key="modelStrong", value="second")

    assert await store.get_all(user_id=_USER_A) == {"modelStrong": "second"}


async def test_service_settings_returns_defaults_when_unset() -> None:
    # Arrange — nothing stored for the user.
    service = UserConfigService(InMemoryUserConfigStore())

    # Act
    settings = await service.settings(user_id=_USER_A)

    # Assert — every per-user key present, each carrying its default value; LangSmith is absent.
    assert {s.name: s.value for s in settings} == {s.name: s.default for s in settings}
    assert {s.name for s in settings} == {
        "modelStrong",
        "modelWorker",
        "videoEnabled",
        "videoLessonsEnabled",
        "videoVoice",
        "videoSummarySeconds",
        "videoOverviewSeconds",
        "videoLessonSeconds",
    }


async def test_service_settings_reflects_a_stored_value() -> None:
    store = InMemoryUserConfigStore()
    await store.set(user_id=_USER_A, key="modelStrong", value="claude-custom")
    service = UserConfigService(store)

    settings = {s.name: s for s in await service.settings(user_id=_USER_A)}

    assert settings["modelStrong"].value == "claude-custom"
    assert settings["modelWorker"].value == settings["modelWorker"].default  # untouched → default


async def test_service_set_persists_and_returns_the_setting() -> None:
    store = InMemoryUserConfigStore()
    service = UserConfigService(store)

    setting = await service.set(user_id=_USER_A, name="modelWorker", value="  claude-fast  ")

    assert setting.value == "claude-fast"  # trimmed
    assert await store.get_all(user_id=_USER_A) == {"modelWorker": "claude-fast"}


async def test_service_rejects_an_operator_only_key() -> None:
    # langsmithTracing is a known config key but NOT per-user — the tenant surface must reject it.
    service = UserConfigService(InMemoryUserConfigStore())

    with pytest.raises(ConfigKeyError):
        await service.set(user_id=_USER_A, name="langsmithTracing", value="true")


async def test_service_rejects_an_unknown_key() -> None:
    service = UserConfigService(InMemoryUserConfigStore())

    with pytest.raises(ConfigKeyError):
        await service.set(user_id=_USER_A, name="nope", value="x")


async def test_service_rejects_an_empty_value() -> None:
    service = UserConfigService(InMemoryUserConfigStore())

    with pytest.raises(ConfigError):
        await service.set(user_id=_USER_A, name="modelStrong", value="   ")


async def test_service_accepts_a_per_user_video_length() -> None:
    # The V6 video keys are per-user; an in-bounds length round-trips through the same surface.
    store = InMemoryUserConfigStore()
    service = UserConfigService(store)

    setting = await service.set(user_id=_USER_A, name="videoLessonSeconds", value="90")

    assert setting.value == "90"
    assert await store.get_all(user_id=_USER_A) == {"videoLessonSeconds": "90"}


async def test_service_rejects_an_out_of_bounds_video_length() -> None:
    # The per-user write boundary re-validates the number range (defence in depth).
    service = UserConfigService(InMemoryUserConfigStore())

    with pytest.raises(ConfigError):
        await service.set(user_id=_USER_A, name="videoLessonSeconds", value="99999")
