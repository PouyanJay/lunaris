"""Covers ``AgentEvent.stage`` tagging via the shared ``StageCursor``: a fine event carries the
pipeline phase active when it fired (so the timeline buckets it), tracks the latest boundary across
phases, and stays ``None`` on the no-stage paths (no cursor, or a cursor nothing ever advances).
"""

from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.stage_cursor import StageCursor
from lunaris_runtime.schema import AgentEvent, AgentEventKind, ProgressStage


class _AgentSink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


async def test_agent_events_carry_the_active_progress_stage() -> None:
    # Arrange — one cursor shared by both reporters (as the runner wires them per run).
    cursor = StageCursor()
    progress = ProgressReporter("run-1", cursor=cursor)
    agent_sink = _AgentSink()
    agent = AgentReporter("run-1", agent_sink, cursor=cursor)

    # Act — a beat before any stage boundary, then a stage is reported, then another beat.
    await agent.emit(AgentEventKind.REASONING, text="Planning the build…")
    await progress.emit(ProgressStage.CONCEPTS_EXTRACTED, "21 concepts")
    await agent.emit(AgentEventKind.TOOL_RESULT, tool="extract_concepts", result="21")

    # Assert — the first beat is unbucketed (intro); the second carries the active phase.
    assert agent_sink.events[0].stage is None
    assert agent_sink.events[1].stage is ProgressStage.CONCEPTS_EXTRACTED


async def test_stage_tracks_the_latest_boundary_across_phases() -> None:
    # Arrange
    cursor = StageCursor()
    progress = ProgressReporter("run-1", cursor=cursor)
    sink = _AgentSink()
    agent = AgentReporter("run-1", sink, cursor=cursor)

    # Act — advance through two phases, emitting a beat in each.
    await progress.emit(ProgressStage.CONCEPTS_EXTRACTED, "concepts")
    await agent.emit(AgentEventKind.TOOL_CALL, tool="build_prerequisite_graph")
    await progress.emit(ProgressStage.GRAPH_BUILT, "graph")
    await agent.emit(AgentEventKind.TOOL_RESULT, tool="build_prerequisite_graph", result="ok")

    # Assert — each beat carries whichever phase was latest when it fired.
    assert sink.events[0].stage is ProgressStage.CONCEPTS_EXTRACTED
    assert sink.events[1].stage is ProgressStage.GRAPH_BUILT


async def test_agent_event_stage_is_none_without_a_cursor() -> None:
    # Arrange / Act — no cursor wired at all (a unit caller).
    sink = _AgentSink()
    await AgentReporter("run-1", sink).emit(AgentEventKind.REASONING, text="hi")

    # Assert — the optional stage simply stays None; nothing breaks.
    assert sink.events[0].stage is None


async def test_agent_event_stage_is_none_when_cursor_never_advances() -> None:
    # Arrange — the batch path: an agent sink is wired but no ProgressReporter advances the cursor.
    cursor = StageCursor()
    sink = _AgentSink()
    agent = AgentReporter("run-1", sink, cursor=cursor)

    # Act
    await agent.emit(AgentEventKind.REASONING, text="no stage context")

    # Assert — the cursor stayed at None, so the event is unbucketed.
    assert sink.events[0].stage is None
