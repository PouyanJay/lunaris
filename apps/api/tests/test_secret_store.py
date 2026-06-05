"""The secret store is the security core: write-only (status never carries the value), applied
to the runtime env so adapters pick it up, and persisted to the gitignored ``.env`` file — the
single source of truth, loaded at startup via ``uv run --env-file .env``. The file is forced to
0600 after every write and control characters are rejected (``.env`` line-injection)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from lunaris_api.secrets import KNOWN_SECRETS, SecretStore


@pytest.fixture(autouse=True)
def _restore_secret_env() -> Iterator[None]:
    # The store writes os.environ directly; snapshot + restore so tests don't leak keys.
    saved = {var: os.environ.get(var) for var in KNOWN_SECRETS.values()}
    yield
    for var, value in saved.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def test_set_upserts_env_line_applies_to_env_and_status_hides_the_value(tmp_path: Path) -> None:
    # Arrange
    env_file = tmp_path / ".env"
    store = SecretStore(env_file)

    # Act
    status = store.set("anthropic", "sk-ant-supersecret-9421")

    # Assert — status reveals only set + last4; the value reaches both the .env file and the env.
    assert status.is_set is True
    assert status.last4 == "9421"
    assert dotenv_values(env_file)["ANTHROPIC_API_KEY"] == "sk-ant-supersecret-9421"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-supersecret-9421"
    assert store.reveal("anthropic") == "sk-ant-supersecret-9421"
    # A SecretStatus carries no value attribute at all.
    assert not any(hasattr(s, "value") for s in store.statuses())


def test_set_preserves_other_env_lines(tmp_path: Path) -> None:
    # Arrange — a pre-existing, unrelated line must survive an upsert untouched.
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=INFO\n")

    # Act
    SecretStore(env_file).set("search", "tvly-dev-abcd")

    # Assert — both lines present; the unrelated one is intact.
    values = dotenv_values(env_file)
    assert values["LOG_LEVEL"] == "INFO"
    assert values["SEARCH_API_KEY"] == "tvly-dev-abcd"


def test_persists_to_owner_only_file_and_reloads(tmp_path: Path) -> None:
    # Arrange / Act
    env_file = tmp_path / ".env"
    SecretStore(env_file).set("voyage", "pa-embed-7777")

    # Assert — file is 0600 (owner read/write only) and a fresh store reloads + re-applies it.
    assert (env_file.stat().st_mode & 0o777) == 0o600
    os.environ.pop("EMBEDDINGS_API_KEY", None)  # prove construction re-applies from the file
    reloaded = SecretStore(env_file)
    assert reloaded.reveal("voyage") == "pa-embed-7777"
    assert os.environ["EMBEDDINGS_API_KEY"] == "pa-embed-7777"


def test_set_forces_0600_even_on_a_preexisting_world_readable_env(tmp_path: Path) -> None:
    # Arrange — an existing 0644 .env (set_key preserves mode, so the store must tighten it).
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=INFO\n")
    env_file.chmod(0o644)

    # Act
    SecretStore(env_file).set("anthropic", "sk-ant-tighten-1111")

    # Assert — the store restored owner-only perms despite the pre-existing world-readable file.
    assert (env_file.stat().st_mode & 0o777) == 0o600


def test_a_manually_edited_env_value_surfaces_as_set(tmp_path: Path) -> None:
    # Arrange — a key written straight into .env (no UI), as an operator would.
    env_file = tmp_path / ".env"
    env_file.write_text("SEARCH_API_KEY=tvly-dev-manual-3333\n")

    # Act
    store = SecretStore(env_file)

    # Assert — the store reads the file fresh, so the manual value shows as set.
    search = next(s for s in store.statuses() if s.name == "search")
    assert search.is_set is True
    assert search.last4 == "3333"


def test_re_set_upserts_rather_than_appends(tmp_path: Path) -> None:
    # Setting the same secret twice must replace the line, not append a second one.
    env_file = tmp_path / ".env"
    store = SecretStore(env_file)
    store.set("anthropic", "sk-ant-first-1111")

    store.set("anthropic", "sk-ant-second-2222")

    assert env_file.read_text().count("ANTHROPIC_API_KEY") == 1
    assert dotenv_values(env_file)["ANTHROPIC_API_KEY"] == "sk-ant-second-2222"


def test_clear_removes_value_from_file_and_env_and_survives_reload(tmp_path: Path) -> None:
    # Arrange
    env_file = tmp_path / ".env"
    store = SecretStore(env_file)
    store.set("anthropic", "sk-ant-to-clear-0000")

    # Act
    status = store.clear("anthropic")

    # Assert — gone from the status, the env, and the .env file.
    assert status.is_set is False
    assert store.reveal("anthropic") is None
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" not in dotenv_values(env_file)

    # And a fresh process (new store) does not re-populate the env from a stale line.
    reloaded = SecretStore(env_file)
    assert reloaded.reveal("anthropic") is None
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_clear_when_absent_is_a_noop(tmp_path: Path) -> None:
    # Clearing a never-set secret must not raise, must report unset, and must not create the file.
    env_file = tmp_path / ".env"
    store = SecretStore(env_file)

    status = store.clear("youtube")

    assert status.is_set is False
    assert not env_file.exists()


def test_empty_value_is_rejected(tmp_path: Path) -> None:
    # An empty value must not silently persist a blank .env line or env var.
    env_file = tmp_path / ".env"
    store = SecretStore(env_file)

    with pytest.raises(ValueError):
        store.set("anthropic", "")

    assert "ANTHROPIC_API_KEY" not in os.environ
    assert not env_file.exists()


@pytest.mark.parametrize("bad", ["line\none", "tab\tval", "null\x00byte", "carriage\rreturn"])
def test_control_characters_are_rejected(tmp_path: Path, bad: str) -> None:
    # A newline/control char could inject extra lines into .env — reject at the store boundary.
    store = SecretStore(tmp_path / ".env")

    with pytest.raises(ValueError):
        store.set("anthropic", bad)

    # And nothing was written / applied.
    assert "ANTHROPIC_API_KEY" not in dotenv_values(tmp_path / ".env")
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_set_creates_a_missing_parent_directory(tmp_path: Path) -> None:
    # A custom LUNARIS_ENV_FILE may point into a not-yet-existing dir; set() must create it
    # rather than surfacing a cryptic FileNotFoundError from the underlying temp-file write.
    env_file = tmp_path / "nested" / "dir" / ".env"

    SecretStore(env_file).set("youtube", "yt-key-9999")

    assert dotenv_values(env_file)["YOUTUBE_API_KEY"] == "yt-key-9999"
    assert (env_file.stat().st_mode & 0o777) == 0o600


def test_unknown_secret_is_rejected(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / ".env")

    with pytest.raises(KeyError):
        store.set("totally_unknown", "x")
