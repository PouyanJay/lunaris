"""The three-minute budget, and the two things that decide whether it holds.

A cold compile is one decomposition call plus one per concept. Whether that fits depends entirely on
the authoring calls overlapping — run serially, fifteen concepts at two seconds each is half a
minute of pure waiting for no reason. So concurrency is not an optimisation here, it is the budget.

These use a model that sleeps rather than a real one: the point is the shape of the work, not the
provider's speed, and a test that depended on a provider's speed would be a flake.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import ClaudeGraphCompiler

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


class SlowModel:
    """A model that takes ``delay`` seconds per call and records how many ran at once."""

    def __init__(self, responses: list[str], *, delay: float) -> None:
        self._responses = list(responses)
        self._delay = delay
        self.in_flight = 0
        self.peak_in_flight = 0
        self.calls = 0

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.calls += 1
        try:
            await asyncio.sleep(self._delay)
            return AIMessage(content=self._responses.pop(0))
        finally:
            self.in_flight -= 1


def _model(concepts: int, *, delay: float) -> SlowModel:
    return SlowModel(
        [json.dumps(_decomposition(concepts)), *[json.dumps(_SPEC)] * concepts], delay=delay
    )


async def test_authoring_the_concepts_overlaps_instead_of_queueing() -> None:
    """The load-bearing property of the whole budget: twelve concepts must not be twelve waits.

    Asserted through the high-water mark rather than elapsed time. asyncio is cooperatively
    scheduled on one thread, so the peak is exact and identical on an idle laptop and a loaded CI
    box — where a wall-clock threshold is precisely the kind of assertion that flakes. It is also
    the stronger claim: elapsed time only shows *some* overlap, this shows the cap was reached.
    """
    # Arrange
    model = _model(12, delay=0.01)
    compiler = ClaudeGraphCompiler("m", client=model, max_concurrency=8)

    # Act
    await compiler.compile("Topic", graph_id="g1", run_id="r1")

    # Assert — decompose is serial by necessity (everything depends on it); authoring is not.
    assert model.calls == 13
    assert model.peak_in_flight == 8, "authoring did not run concurrently up to the cap"


async def test_authoring_never_exceeds_the_configured_concurrency() -> None:
    """The cap is what keeps a large graph from bursting past the provider's rate limit — the
    failure it prevents is a 429 storm mid-compile, which no retry budget recovers gracefully."""
    # Arrange
    model = _model(12, delay=0.02)

    # Act
    await ClaudeGraphCompiler("m", client=model, max_concurrency=3).compile(
        "Topic", graph_id="g1", run_id="r1"
    )

    # Assert
    # Equality, not `<=`: a regression to fully serial authoring would also satisfy `<= 3`.
    assert model.peak_in_flight == 3


async def test_a_compile_that_overruns_its_budget_is_abandoned() -> None:
    """A request that hangs is worse than one that fails: the learner waits with no way to know
    it is never coming, and the work goes on spending tokens behind them."""
    # Arrange — one concept, but the model never answers inside the budget.
    model = _model(1, delay=5)
    compiler = ClaudeGraphCompiler("m", client=model, deadline_s=0.1)

    # Act / Assert
    with pytest.raises(TimeoutError):
        await compiler.compile("Topic", graph_id="g1", run_id="r1")


async def test_the_budget_is_generous_enough_not_to_fire_on_a_normal_compile() -> None:
    # Arrange
    model = _model(4, delay=0.01)

    # Act
    graph = await ClaudeGraphCompiler("m", client=model, deadline_s=5).compile(
        "Topic", graph_id="g1", run_id="r1"
    )

    # Assert
    assert len(graph.nodes) == 4
