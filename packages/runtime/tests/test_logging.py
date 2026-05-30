import json

import pytest
import structlog
from lunaris_runtime.logging import bind_run_id, clear_correlation, configure_logging


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
