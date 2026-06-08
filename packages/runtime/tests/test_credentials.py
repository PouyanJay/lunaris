import asyncio

from lunaris_runtime.credentials import resolve_secret, run_credentials


def test_no_scope_falls_back_to_env(monkeypatch) -> None:
    # Arrange — no run scope active, the env var is set (admin/eval/single-user path).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

    # Act / Assert — resolve_secret reads the process env, exactly as today.
    assert resolve_secret("ANTHROPIC_API_KEY") == "env-key"


def test_no_scope_unset_env_is_none(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    assert resolve_secret("SEARCH_API_KEY") is None


def test_scope_overrides_env(monkeypatch) -> None:
    # Arrange — a platform key is in env, but a tenant scope is active with the tenant's own key.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    # Act / Assert — the tenant's key wins; the platform env key never leaks into the build.
    with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
        assert resolve_secret("ANTHROPIC_API_KEY") == "tenant-key"
    # Restored on exit.
    assert resolve_secret("ANTHROPIC_API_KEY") == "platform-key"


def test_scope_without_key_does_not_fall_back_to_env(monkeypatch) -> None:
    # Tenant-only: inside a scope, a provider the tenant has NOT set resolves to None — it must NOT
    # fall through to the platform env key (that would silently bill the platform / leak the key).
    monkeypatch.setenv("SEARCH_API_KEY", "platform-search-key")

    with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
        assert resolve_secret("SEARCH_API_KEY") is None


def test_empty_scope_value_is_none(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_API_KEY", "platform")

    with run_credentials({"EMBEDDINGS_API_KEY": ""}):
        assert resolve_secret("EMBEDDINGS_API_KEY") is None


def test_scope_is_inherited_by_a_child_task(monkeypatch) -> None:
    # The build runs in a separate asyncio.Task created within the scope; contextvars are copied
    # into the child at creation, so the tenant's keys reach the lazily-built adapters in the run.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    async def scenario() -> str | None:
        async def read_in_task() -> str | None:
            return resolve_secret("ANTHROPIC_API_KEY")

        with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
            task = asyncio.create_task(read_in_task())
        # Scope exited in the parent BEFORE the task is awaited — the task keeps its own context
        # copy (create_task snapshots the context at creation), so it still sees the tenant key.
        return await task

    assert asyncio.run(scenario()) == "tenant-key"
