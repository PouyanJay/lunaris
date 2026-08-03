"""The model-backed compiler: a topic in, a teachable map out.

The model is scripted, so these are about what the compiler does with a response — not about
response quality, which is the keyed eval at T9. What matters here is that the compiler is
*defensive*: a decomposition is inference, it will come back malformed sooner or later, and the
difference between a degraded graph and a failed compile is a learner's whole session.
"""

import json

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import (
    ClaudeGraphCompiler,
    GraphCompilationError,
    MasteryCriterionKind,
    NodeProvenance,
)

_DECOMPOSITION = {
    "concepts": [
        {
            "id": "slope",
            "name": "Derivative as slope",
            "definition": "How steeply…",
            "requires": [],
        },
        {"id": "loss", "name": "Loss function", "definition": "One number…", "requires": []},
        {
            "id": "gradient",
            "name": "Gradient",
            "definition": "The slope of the loss…",
            "requires": ["slope", "loss"],
        },
    ]
}

_SPEC = {
    "objective": "Say which way is downhill and how steep it is there.",
    "misconceptions": ["A derivative is a formula to memorise, not a slope you can see."],
    "depth": "intuition_first",
    "criteria": [
        {"kind": "predict", "statement": "Point at a curve and say which way lowers it."},
        {
            "kind": "manipulate",
            "statement": "Drive the rate up until it diverges.",
            "needsSim": True,
        },
    ],
}


class ScriptedModel:
    """Replays responses in order and records prompts; fails loudly if over-called."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("scripted model exhausted — unexpected extra call")
        return AIMessage(content=self._responses.pop(0))


def _model(*, decomposition: object = _DECOMPOSITION, specs: int = 3) -> ScriptedModel:
    return ScriptedModel([json.dumps(decomposition), *[json.dumps(_SPEC)] * specs])


async def _compiled(model: ScriptedModel) -> object:
    return await ClaudeGraphCompiler("m", client=model).compile(
        "How neural networks learn", graph_id="g1", run_id="r1"
    )


async def test_a_topic_becomes_a_graph_of_named_concepts() -> None:
    # Act
    graph = await _compiled(_model())

    # Assert
    assert [node.name for node in graph.nodes] == [
        "Derivative as slope",
        "Loss function",
        "Gradient",
    ]
    assert graph.topic == "How neural networks learn"


async def test_the_dependencies_the_model_claimed_are_assembled_into_an_order() -> None:
    # Act
    graph = await _compiled(_model())

    # Assert — assembly still owns the structure; the model only proposed it.
    assert graph.is_acyclic is True
    assert graph.topo_order.index("slope") < graph.topo_order.index("gradient")
    assert graph.topo_order.index("loss") < graph.topo_order.index("gradient")


async def test_every_concept_is_given_a_teaching_spec_and_something_to_prove() -> None:
    # Act
    graph = await _compiled(_model())

    # Assert — the authored half of a node, which is what the whole product later reads.
    for node in graph.nodes:
        assert node.teaching_spec is not None
        assert node.teaching_spec.misconceptions
        assert node.mastery_criteria
        assert node.mastery_criteria[0].kind is MasteryCriterionKind.PREDICT

    # A criterion needing a simulator is recorded as such — that is how Phase 3 knows what to build.
    assert any(c.needs_sim for node in graph.nodes for c in node.mastery_criteria)


async def test_a_cold_compile_marks_every_node_compiled() -> None:
    graph = await _compiled(_model())

    assert {node.provenance for node in graph.nodes} == {NodeProvenance.COMPILED}


async def test_the_topic_reaches_the_model() -> None:
    # Arrange
    model = _model()

    # Act
    await _compiled(model)

    # Assert — the decomposition prompt is the first call and carries the learner's actual words.
    assert "How neural networks learn" in model.prompts[0]


async def test_prose_around_the_json_is_tolerated() -> None:
    """Models preface JSON with commentary. That is a parsing problem, not a compile failure."""
    # Arrange
    model = ScriptedModel(
        [
            f"Sure! Here it is:\n```json\n{json.dumps(_DECOMPOSITION)}\n```\nHope that helps.",
            *[json.dumps(_SPEC)] * 3,
        ]
    )

    # Act
    graph = await _compiled(model)

    # Assert
    assert len(graph.nodes) == 3


async def test_a_concept_missing_a_definition_is_dropped_not_invented() -> None:
    """A half-formed concept is worse than a missing one: the tutor would teach the gap."""
    # Arrange
    decomposition = {
        "concepts": [
            {"id": "ok", "name": "Fine", "definition": "A real definition.", "requires": []},
            {"id": "bad", "name": "Nameless", "requires": []},
        ]
    }
    model = ScriptedModel([json.dumps(decomposition), json.dumps(_SPEC)])

    # Act
    graph = await _compiled(model)

    # Assert
    assert [node.id for node in graph.nodes] == ["ok"]


async def test_an_unparseable_decomposition_fails_the_compile() -> None:
    """The one thing that cannot degrade gracefully: with no concepts there is no map, and
    returning an empty graph would present a failure as a finished product."""
    # Arrange
    model = ScriptedModel(["I'm afraid I can't do that."])

    # Act / Assert
    with pytest.raises(GraphCompilationError, match="decompos"):
        await _compiled(model)


async def test_a_failed_spec_leaves_the_concept_standing() -> None:
    """One authoring failure must not condemn the whole compile — the concept is still real, and a
    node without a spec is teachable-in-principle. Losing the map would cost far more."""
    # Arrange — the second spec call comes back as junk.
    model = ScriptedModel(
        [json.dumps(_DECOMPOSITION), json.dumps(_SPEC), "not json at all", json.dumps(_SPEC)]
    )

    # Act
    graph = await _compiled(model)

    # Assert — every concept survives; the one that failed simply has no spec yet.
    assert len(graph.nodes) == 3
    assert sum(1 for node in graph.nodes if node.teaching_spec is None) == 1


async def test_a_criterion_of_an_unknown_kind_is_dropped_rather_than_guessed() -> None:
    # Arrange — the runtime keys its move off the kind, so a wrong one is worse than none.
    spec = {**_SPEC, "criteria": [{"kind": "vibes", "statement": "Feel it."}]}
    model = ScriptedModel([json.dumps(_DECOMPOSITION), *[json.dumps(spec)] * 3])

    # Act
    graph = await _compiled(model)

    # Assert
    assert all(node.mastery_criteria == [] for node in graph.nodes)
    assert all(node.teaching_spec is not None for node in graph.nodes)


async def test_a_repeated_concept_id_is_kept_once() -> None:
    """Two concepts under one id is quietly destructive: ordering is derived over a *set* of ids,
    so the duplicate would vanish from the order while still sitting in the node list — a concept
    on the map that the session can never reach."""
    # Arrange
    decomposition = {
        "concepts": [
            {"id": "dup", "name": "First", "definition": "One.", "requires": []},
            {"id": "dup", "name": "Second", "definition": "Two.", "requires": []},
        ]
    }
    model = ScriptedModel([json.dumps(decomposition), json.dumps(_SPEC)])

    # Act
    graph = await _compiled(model)

    # Assert — first occurrence wins, and the map stays internally consistent.
    assert [node.name for node in graph.nodes] == ["First"]
    assert len(graph.topo_order) == len(graph.nodes)


async def test_a_decomposition_with_no_concepts_fails_the_compile() -> None:
    """Valid JSON saying "nothing here" is still no map — a distinct branch from unparseable."""
    # Arrange
    model = ScriptedModel([json.dumps({"concepts": []})])

    # Act / Assert
    with pytest.raises(GraphCompilationError):
        await _compiled(model)


async def test_a_concept_that_is_not_an_object_is_skipped() -> None:
    # Arrange — a stray null, the shape a trailing comma tends to produce.
    decomposition = {
        "concepts": [
            None,
            "gradient",
            {"id": "ok", "name": "Fine", "definition": "Real.", "requires": []},
        ]
    }
    model = ScriptedModel([json.dumps(decomposition), json.dumps(_SPEC)])

    # Act
    graph = await _compiled(model)

    # Assert
    assert [node.id for node in graph.nodes] == ["ok"]


async def test_an_over_long_field_is_clamped_rather_than_failing_the_compile() -> None:
    """A model that runs long must cost a truncated definition, not the whole map. Unclamped, this
    fails validation inside a gathered task and escapes as a 500 with no run id attached."""
    # Arrange — every field past its contract limit.
    decomposition = {
        "concepts": [
            {
                "id": "x" * 300,
                "name": "y" * 400,
                "definition": "z" * 5000,
                "requires": [],
            }
        ]
    }
    model = ScriptedModel([json.dumps(decomposition), json.dumps(_SPEC)])

    # Act
    graph = await _compiled(model)

    # Assert
    node = graph.nodes[0]
    assert (len(node.id), len(node.name), len(node.definition)) == (100, 200, 2000)


async def test_one_concept_failing_to_author_does_not_lose_the_others() -> None:
    """A transient provider error on one of a dozen concurrent calls is close to expected. The
    documented contract is that it costs that concept's notes, never the map."""

    # Arrange — the second authoring call raises the way a real client does.
    class FlakyModel(ScriptedModel):
        async def ainvoke(self, prompt: str) -> AIMessage:
            self.prompts.append(prompt)
            if len(self.prompts) == 3:
                raise RuntimeError("upstream said no")
            return AIMessage(content=self._responses.pop(0))

    model = FlakyModel([json.dumps(_DECOMPOSITION), json.dumps(_SPEC), json.dumps(_SPEC)])

    # Act
    graph = await _compiled(model)

    # Assert — every concept survives; exactly one is left without its notes.
    assert len(graph.nodes) == 3
    assert sum(1 for node in graph.nodes if node.teaching_spec is None) == 1


async def test_a_fence_marker_inside_a_value_is_not_stripped_out_of_it() -> None:
    """Content the model wrote must survive normalisation intact. Anchoring the fence strip
    per-line silently ate ``` sequences from inside string values."""
    # Arrange
    spec = {**_SPEC, "objective": "Read a loss curve, like ```this``` one, and diagnose it."}
    model = ScriptedModel([json.dumps(_DECOMPOSITION), *[json.dumps(spec)] * 3])

    # Act
    graph = await _compiled(model)

    # Assert
    assert graph.nodes[0].teaching_spec is not None
    assert "```this```" in graph.nodes[0].teaching_spec.objective


async def test_trailing_prose_containing_a_brace_is_ignored() -> None:
    # Arrange — decoding forward from the first brace, rather than slicing to the last one.
    model = ScriptedModel(
        [
            json.dumps(_DECOMPOSITION) + "\n\nLet me know if you want changes {or anything else}.",
            *[json.dumps(_SPEC)] * 3,
        ]
    )

    # Act
    graph = await _compiled(model)

    # Assert
    assert len(graph.nodes) == 3
