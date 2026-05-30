"""The secret store is the security core: write-only (status never carries the value), applied
to the runtime env so adapters pick it up, and persisted to an owner-only (0600) file."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
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


def test_set_applies_to_env_and_status_hides_the_value(tmp_path: Path) -> None:
    # Arrange
    store = SecretStore(tmp_path / "secrets.json")

    # Act
    status = store.set("anthropic", "sk-ant-supersecret-9421")

    # Assert — status reveals only set + last4; the value reaches the env; reveal is internal.
    assert status.is_set is True
    assert status.last4 == "9421"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-supersecret-9421"
    assert store.reveal("anthropic") == "sk-ant-supersecret-9421"
    # A SecretStatus carries no value attribute at all.
    assert not any(hasattr(s, "value") for s in store.statuses())


def test_persists_to_owner_only_file_and_reloads(tmp_path: Path) -> None:
    # Arrange / Act
    path = tmp_path / "secrets.json"
    SecretStore(path).set("voyage", "pa-embed-7777")

    # Assert — file is 0600 (owner read/write only) and a fresh store reloads + re-applies it.
    assert (path.stat().st_mode & 0o777) == 0o600
    reloaded = SecretStore(path)
    assert reloaded.reveal("voyage") == "pa-embed-7777"
    assert os.environ["EMBEDDINGS_API_KEY"] == "pa-embed-7777"


def test_clear_removes_value_and_env(tmp_path: Path) -> None:
    # Arrange
    store = SecretStore(tmp_path / "secrets.json")
    store.set("anthropic", "sk-ant-to-clear-0000")

    # Act
    status = store.clear("anthropic")

    # Assert
    assert status.is_set is False
    assert store.reveal("anthropic") is None
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_unknown_secret_is_rejected(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")

    with pytest.raises(KeyError):
        store.set("totally_unknown", "x")
