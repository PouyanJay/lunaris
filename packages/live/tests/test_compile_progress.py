"""What a compile says about itself while it is still running.

A cold compile takes minutes, and the screen a learner spends that time on is the compile itself.
"Working on it" is not honest for three minutes — the compiler is the only thing that knows how many
concepts there are and how many have been written, so it is the only thing that can say. These tests
pin that it reports *as it goes* rather than handing over a summary at the end, which is the whole
difference between a progress bar and a spinner wearing one.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import ClaudeGraphCompiler, CompilePhase, CompileProgress

_SPEC = {
    "objective": "Do the thing.",
    "misconceptions": ["A wrong belief."],
    "depth": "intuition_first",
    "criteria": [{"kind": "predict", "statement": "Say what happens."}],
}


def _decomposition(count: int) -> dict[str, object]:
    return {
        "concepts": [
            {"id": f"c{i}", "name": f"Concept {i}", "definition": "A definition.", "requires": []}
            for i in range(count)
        ]
    }


class ScriptedModel:
    """Answers the decomposition then one spec per concept, with a beat between calls so the
    authoring genuinely interleaves rather than completing inside one scheduling slot."""

    def __init__(self, concepts: int) -> None:
        self._responses = [
            json.dumps(_decomposition(concepts)),
            *[json.dumps(_SPEC)] * concepts,
        ]

    async def ainvoke(self, prompt: str) -> AIMessage:
        await asyncio.sleep(0.01)
        return AIMessage(content=self._responses.pop(0))


def _compiler(concepts: int, **kwargs: object) -> ClaudeGraphCompiler:
    return ClaudeGraphCompiler("m", client=ScriptedModel(concepts), **kwargs)  # type: ignore[arg-type]


async def test_the_decomposition_is_announced_before_any_concept_is_authored() -> None:
    """The first minute of a compile has nothing to count yet — say what is happening instead.

    Without this the screen sits at zero for the whole decomposition and then jumps, which reads as
    a stall in exactly the stretch a learner is most likely to abandon.
    """
    # Arrange
    reported: list[CompileProgress] = []

    # Act
    await _compiler(3).compile("Topic", graph_id="g1", run_id="r1", on_progress=reported.append)

    # Assert
    assert reported[0].phase is CompilePhase.DECOMPOSING
    assert reported[0].total == 0, "nothing is countable before the concepts are known"


async def test_authoring_counts_each_concept_off_against_the_total() -> None:
    # Arrange
    reported: list[CompileProgress] = []

    # Act
    await _compiler(4).compile("Topic", graph_id="g1", run_id="r1", on_progress=reported.append)

    # Assert — every concept accounted for, in order, against a total known from decomposition.
    authoring = [event for event in reported if event.phase is CompilePhase.AUTHORING]
    assert [event.done for event in authoring] == [1, 2, 3, 4]
    assert {event.total for event in authoring} == {4}


async def test_progress_is_reported_while_the_compile_is_still_running() -> None:
    """The load-bearing claim, and the one that cannot be tested by looking at what arrived.

    A compiler that buffered its beats and emitted them in a burst just before returning would
    satisfy every assertion above — same events, same order, same counts — and still leave the
    learner watching a frozen bar for three minutes. Collecting events and inspecting them after
    ``compile`` returns therefore proves nothing about *when* they were sent.

    So the compile is made to depend on its own progress instead: every spec call after the first
    blocks until a partial count has been reported. If beats only arrived at the end, the compile
    could never reach the end — it would deadlock, and the timeout below is what says so.
    """
    # Arrange
    seen_partial = asyncio.Event()

    def report(event: CompileProgress) -> None:
        if event.phase is CompilePhase.AUTHORING and 0 < event.done < event.total:
            seen_partial.set()

    class GatedModel(ScriptedModel):
        """Answers the decomposition and one spec freely; every later spec waits to be told that a
        partial count has already gone out."""

        def __init__(self, concepts: int) -> None:
            super().__init__(concepts)
            self._answered = 0

        async def ainvoke(self, prompt: str) -> AIMessage:
            self._answered += 1
            if self._answered > 2:  # 1 = decomposition, 2 = the concept that unblocks the rest
                await seen_partial.wait()
            return await super().ainvoke(prompt)

    compiler = ClaudeGraphCompiler("m", client=GatedModel(4), max_concurrency=8)

    # Act — bounded, because the failure mode being pinned is a compile that never finishes.
    try:
        graph = await asyncio.wait_for(
            compiler.compile("Topic", graph_id="g1", run_id="r1", on_progress=report), timeout=2.0
        )
    except TimeoutError:  # pragma: no cover - only reached when the behaviour regresses
        pytest.fail("the compile stalled waiting for a beat that was buffered until the end")

    # Assert
    assert seen_partial.is_set()
    assert len(graph.nodes) == 4, "the compile completed on the strength of its own progress"


async def test_the_finished_map_is_the_last_thing_reported() -> None:
    """Assembly is fast but it is not free, and it is where the graph stops being a list of
    concepts and becomes ordered. Reporting it keeps the bar from sitting at 100% saying nothing."""
    # Arrange
    reported: list[CompileProgress] = []

    # Act
    graph = await _compiler(3).compile(
        "Topic", graph_id="g1", run_id="r1", on_progress=reported.append
    )

    # Assert
    assert reported[-1].phase is CompilePhase.ASSEMBLING
    assert reported[-1].done == reported[-1].total == len(graph.nodes)


async def test_a_sink_that_fails_does_not_take_the_compile_with_it() -> None:
    """Progress is telemetry about the work, not the work. A dropped connection mid-compile must
    cost the learner their progress bar, never the map they waited three minutes for."""

    # Arrange
    def report(event: CompileProgress) -> None:
        raise RuntimeError("the client went away")

    # Act
    graph = await _compiler(3).compile("Topic", graph_id="g1", run_id="r1", on_progress=report)

    # Assert
    assert len(graph.nodes) == 3


async def test_a_compile_with_nobody_listening_still_compiles() -> None:
    """The sink is optional: the POST entry point (and every existing caller) passes none."""
    # Act
    graph = await _compiler(2).compile("Topic", graph_id="g1", run_id="r1")

    # Assert
    assert len(graph.nodes) == 2
