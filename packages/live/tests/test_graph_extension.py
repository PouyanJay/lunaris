"""C1 — growing the map mid-session.

The constraint this exists to satisfy: a learner will ask for somewhere the compiled map does not
go, and if the only way to get there is a fresh three-minute compile, the tutor's realistic options
are to refuse or to railroad. So the map has to grow on one branch, inside a pause someone can talk
over, without ever putting the settled part of the graph at risk.

Those are the two halves pinned here — that an extension *works*, and that it cannot damage what was
already there.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import (
    ClaudeGraphCompiler,
    ConceptGraph,
    ConceptNode,
    GraphCompilationError,
    NodeProvenance,
)

_SPEC = {
    "objective": "Do the thing.",
    "misconceptions": ["A wrong belief."],
    "depth": "applied",
    "criteria": [{"kind": "predict", "statement": "Say what happens."}],
}

_BRANCH = {
    "concepts": [
        {
            "id": "picking-a-rate",
            "name": "Picking a learning rate in practice",
            "definition": "How to choose a step size for a real project.",
            "requires": ["learning-rate"],
        }
    ]
}


class ScriptedModel:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("scripted model exhausted — unexpected extra call")
        return AIMessage(content=self._responses.pop(0))


def _node(node_id: str, *requires: str) -> ConceptNode:
    return ConceptNode(id=node_id, name=node_id, definition="d", requires=list(requires))


def _compiled() -> ConceptGraph:
    """A settled two-concept map, the way a cold compile leaves it."""
    return ConceptGraph(
        graph_id="g1",
        topic="How neural networks learn",
        version=1,
        nodes=[_node("loss"), _node("learning-rate", "loss")],
        topo_order=["loss", "learning-rate"],
        is_acyclic=True,
    )


async def _extended(model: ScriptedModel, *, request: str = "How do I pick one for my project?"):
    return await ClaudeGraphCompiler("m", client=model).extend(
        _compiled(), request=request, anchors=["learning-rate"], run_id="r2"
    )


async def test_a_request_the_map_does_not_cover_adds_a_concept_to_it() -> None:
    # Act
    graph = await _extended(ScriptedModel([json.dumps(_BRANCH), json.dumps(_SPEC)]))

    # Assert — the new concept is on the map, hung off what the learner already has.
    added = next(node for node in graph.nodes if node.id == "picking-a-rate")
    assert added.requires == ["learning-rate"]
    assert graph.topo_order[-1] == "picking-a-rate"
    assert graph.is_acyclic is True


async def test_an_added_concept_is_marked_as_extended() -> None:
    """The one distinction a session must be able to draw later: what the compiler chose to teach
    versus what the learner's own question put there."""
    # Act
    graph = await _extended(ScriptedModel([json.dumps(_BRANCH), json.dumps(_SPEC)]))

    # Assert
    by_id = {node.id: node for node in graph.nodes}
    assert by_id["picking-a-rate"].provenance is NodeProvenance.EXTENDED
    assert by_id["learning-rate"].provenance is NodeProvenance.COMPILED


async def test_an_extension_bumps_the_version_and_records_why() -> None:
    # Act
    graph = await _extended(
        ScriptedModel([json.dumps(_BRANCH), json.dumps(_SPEC)]),
        request="Forget the maths, how do I pick one for my project?",
    )

    # Assert — the graph is a versioned object with a history, not a rebuilt artifact.
    assert graph.version == 2
    assert len(graph.edits) == 1
    edit = graph.edits[0]
    assert edit.version == 2
    assert edit.request == "Forget the maths, how do I pick one for my project?"
    assert edit.added == ["picking-a-rate"]
    assert edit.anchors == ["learning-rate"]


async def test_the_learners_own_words_reach_the_model() -> None:
    # Arrange
    model = ScriptedModel([json.dumps(_BRANCH), json.dumps(_SPEC)])

    # Act
    await _extended(model, request="what about momentum")

    # Assert — and the map it already has, so the extension is scoped rather than duplicative.
    assert "what about momentum" in model.prompts[0]
    assert "learning-rate" in model.prompts[0]


async def test_an_extension_cannot_change_what_the_settled_map_depends_on() -> None:
    """The invariant that makes growing a map safe: an extension is append-only.

    A model asked to extend will sometimes rewrite what it was shown — here it tries to give an
    existing concept a new prerequisite. Honouring that would let a mid-session question silently
    re-sequence a course the learner is partway through.
    """
    # Arrange — the response restates an existing concept with different dependencies.
    meddling = {
        "concepts": [
            {
                "id": "loss",
                "name": "Loss",
                "definition": "Rewritten.",
                "requires": ["learning-rate"],
            },
            {
                "id": "picking-a-rate",
                "name": "Picking a rate",
                "definition": "New.",
                "requires": ["learning-rate"],
            },
        ]
    }
    model = ScriptedModel([json.dumps(meddling), json.dumps(_SPEC)])

    # Act
    graph = await _extended(model)

    # Assert — the existing concept is untouched, and only the genuinely new one was added.
    by_id = {node.id: node for node in graph.nodes}
    assert by_id["loss"].requires == []
    assert by_id["loss"].definition == "d"
    assert by_id["loss"].provenance is NodeProvenance.COMPILED
    assert "picking-a-rate" in by_id


async def test_an_extension_that_adds_nothing_new_is_refused() -> None:
    """Nothing to add is a failed extension, not a silent no-op: the tutor asked because the map
    did not cover the question, and pretending otherwise strands the learner."""
    # Arrange — everything it proposes already exists.
    model = ScriptedModel(
        [json.dumps({"concepts": [{"id": "loss", "name": "L", "definition": "d"}]})]
    )

    # Act / Assert
    with pytest.raises(GraphCompilationError):
        await _extended(model)


async def test_an_extension_returns_inside_a_conversational_pause() -> None:
    """The budget that makes C1 usable at all: a cold compile is minutes, an extension has to be
    short enough that a tutor can talk over it."""

    # Arrange — a model slower than the extension's own deadline.
    class SlowModel(ScriptedModel):
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(5)
            return await super().ainvoke(prompt)

    compiler = ClaudeGraphCompiler(
        "m", client=SlowModel([json.dumps(_BRANCH)]), extend_deadline_s=0.1
    )

    # Act / Assert
    with pytest.raises(TimeoutError):
        await compiler.extend(_compiled(), request="anything", anchors=[], run_id="r2")


async def test_a_second_extension_appends_to_the_history() -> None:
    # Arrange
    first = await _extended(ScriptedModel([json.dumps(_BRANCH), json.dumps(_SPEC)]))
    second_branch = {
        "concepts": [
            {"id": "momentum", "name": "Momentum", "definition": "Carrying speed.", "requires": []}
        ]
    }

    # Act
    graph = await ClaudeGraphCompiler(
        "m", client=ScriptedModel([json.dumps(second_branch), json.dumps(_SPEC)])
    ).extend(first, request="what about momentum", anchors=[], run_id="r3")

    # Assert — the log is append-only and version-ordered.
    assert graph.version == 3
    assert [edit.version for edit in graph.edits] == [2, 3]
    assert [edit.added for edit in graph.edits] == [["picking-a-rate"], ["momentum"]]
