import json

import pytest
import structlog
from lunaris_runtime.logging import (
    bind_run_id,
    clear_correlation,
    configure_logging,
    redact_sensitive,
)

_REDACTED = "***REDACTED***"


def _json_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def test_bound_run_id_appears_on_every_log_line(capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange — the real configured pipeline (contextvars merge processor carries run_id)
    clear_correlation()
    configure_logging(json_output=True)
    bind_run_id("run-123")
    logger = structlog.get_logger()

    # Act
    logger.info("concept_extraction_started", topic="graphs")
    logger.info("concept_extraction_completed", kc_count=7)
    clear_correlation()

    # Assert
    entries = _json_lines(capsys.readouterr().out)
    assert len(entries) >= 2
    assert all(entry["run_id"] == "run-123" for entry in entries[-2:])


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "api_key",
        "anthropic_api_key",
        "access_token",
        "password",
        "authorization",
        "service_role_key",
    ],
)
def test_redact_sensitive_masks_known_secret_keys(sensitive_key: str) -> None:
    # Arrange — an event dict carrying a secret under a representative sensitive key.
    event = {"event": "call", sensitive_key: "super-secret-value"}

    # Act
    result = redact_sensitive(None, "info", event)

    # Assert — the value is masked; the marker, not the secret, is what a sink would see.
    assert result[sensitive_key] == _REDACTED
    assert "super-secret-value" not in json.dumps(result)


def test_redact_sensitive_leaves_operational_fields_intact() -> None:
    # Arrange — ordinary correlation/operational fields must survive (they make logs useful).
    event = {"event": "course_run_completed", "run_id": "r1", "topic": "graphs", "kc_count": 7}

    # Act
    result = redact_sensitive(None, "info", {**event})

    # Assert — unchanged.
    assert result == event


def test_redact_sensitive_recurses_into_nested_secrets() -> None:
    # Arrange — a secret nested under a non-sensitive key (e.g. a logged tool payload).
    event = {
        "event": "tool_call",
        "payload": {"api_key": "k", "model": "claude"},
        "items": [{"token": "t"}],
    }

    # Act
    result = redact_sensitive(None, "info", event)

    # Assert — the nested secrets are masked, the sibling non-secret fields preserved.
    assert result["payload"]["api_key"] == _REDACTED
    assert result["payload"]["model"] == "claude"
    assert result["items"][0]["token"] == _REDACTED


def test_configured_pipeline_redacts_secrets_before_the_sink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange — the REAL configured pipeline (redact_sensitive wired into configure_logging).
    clear_correlation()
    configure_logging(json_output=True)
    bind_run_id("run-redact")
    logger = structlog.get_logger()

    # Act — a stray secret kwarg reaches the logger.
    logger.info("anthropic_call", api_key="sk-ant-leak-me", model="claude-opus-4-8")
    clear_correlation()

    # Assert — the JSON the sink emits carries the marker, never the secret; the run_id + the
    # non-sensitive field still thread through (redaction doesn't break operational logging).
    out = capsys.readouterr().out
    assert "sk-ant-leak-me" not in out
    entry = _json_lines(out)[-1]
    assert entry["api_key"] == _REDACTED
    assert entry["model"] == "claude-opus-4-8"
    assert entry["run_id"] == "run-redact"
