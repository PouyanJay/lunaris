import json
from pathlib import Path

import pytest
from lunaris_agent.orchestrator import Orchestrator
from lunaris_runtime.logging import clear_correlation, configure_logging
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import CourseStatus


def _json_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


async def test_walking_skeleton_persists_course_with_correlated_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — schema, persistence, logging wired together, no network
    clear_correlation()
    configure_logging(json_output=True)
    store = CourseStore(tmp_path)
    orchestrator = Orchestrator(store)

    # Act — the cross-layer roundtrip
    course = await orchestrator.run("binary search", course_id="c1", run_id="run-42")
    clear_correlation()

    # Assert — the pathway walked: built -> persisted -> logged, all under one run_id
    assert course.status is CourseStatus.MAPPING
    assert store.load("c1") == course

    entries = _json_lines(capsys.readouterr().out)
    events = {entry["event"] for entry in entries}
    assert "course_run_started" in events
    assert "course_run_completed" in events
    assert all(entry["run_id"] == "run-42" for entry in entries)
