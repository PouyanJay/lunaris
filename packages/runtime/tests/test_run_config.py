import asyncio

from lunaris_runtime.run_config import resolve_config, run_config


def test_no_scope_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "env-model")

    assert resolve_config("LUNARIS_MODEL_STRONG") == "env-model"


def test_no_scope_unset_is_none(monkeypatch) -> None:
    monkeypatch.delenv("LUNARIS_MODEL_WORKER", raising=False)

    assert resolve_config("LUNARIS_MODEL_WORKER") is None


def test_scope_value_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "operator-model")

    with run_config({"LUNARIS_MODEL_STRONG": "tenant-model"}):
        assert resolve_config("LUNARIS_MODEL_STRONG") == "tenant-model"
    assert resolve_config("LUNARIS_MODEL_STRONG") == "operator-model"


def test_scope_without_value_falls_back_to_env(monkeypatch) -> None:
    # Unlike a secret, a non-secret config not set by the tenant falls back to the operator's env
    # default (then the code default) — there's no billing/leak concern.
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "operator-model")

    with run_config({"LUNARIS_MODEL_WORKER": "tenant-worker"}):  # strong not in scope
        assert resolve_config("LUNARIS_MODEL_STRONG") == "operator-model"


def test_empty_scope_value_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "operator-model")

    with run_config({"LUNARIS_MODEL_STRONG": ""}):
        assert resolve_config("LUNARIS_MODEL_STRONG") == "operator-model"


def test_scope_is_inherited_by_a_child_task(monkeypatch) -> None:
    monkeypatch.setenv("LUNARIS_MODEL_STRONG", "operator-model")

    async def scenario() -> str | None:
        async def read_in_task() -> str | None:
            return resolve_config("LUNARIS_MODEL_STRONG")

        with run_config({"LUNARIS_MODEL_STRONG": "tenant-model"}):
            task = asyncio.create_task(read_in_task())
        return await task

    assert asyncio.run(scenario()) == "tenant-model"
