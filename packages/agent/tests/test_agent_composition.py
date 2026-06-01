"""The agent-pipeline composition root opts into live token streaming.

The live planner is a real streaming model, so ``build_agent_course_builder`` turns token-by-token
reasoning streaming on; the no-key path (constructed directly with a scripted model) leaves it off,
keeping the deterministic ``updates`` transcript stable.
"""

from pathlib import Path

import pytest
from lunaris_agent.composition import build_agent_course_builder
from lunaris_runtime.persistence import CourseStore


def test_live_agent_builder_enables_token_streaming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — a dummy key lets the live planner (ChatAnthropic) construct without a network call.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")

    # Act
    builder = build_agent_course_builder(CourseStore(tmp_path))

    # Assert — the live path streams the agent's reasoning token-by-token (the wiring the runner
    # forwards to the harness tap).
    assert builder.stream_tokens is True
