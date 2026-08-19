"""The prior mapper: from an interview to a placement (Lunaris Live, Phase 2c, T3).

One model call, once the map has landed and the interview has ended, reads the exchanges and the
map and says two things: who this learner is (a paragraph the tutor reads) and which concepts they
already hold (priors, one per node, in [0, 1]). It never invents a node, never rates a node it was
not shown, and its failure is a placement with no priors — the map is still taught, from the root.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import ConceptGraph, ConceptNode
from lunaris_live.session import (
    ClaudePriorMapper,
    InterviewExchange,
    PriorMapperUnavailableError,
    StubPriorMapper,
)

_EXCHANGES = (
    InterviewExchange(
        question="What have you met of Bayes' theorem?",
        answer="I know what a prior is and I've done conditional probability at school.",
    ),
    InterviewExchange(question="What for?", answer="Reading medical test results."),
)


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id="g1",
        topic="Bayes' theorem",
        nodes=[
            ConceptNode(id="prior", name="Prior", definition="What you believed before."),
            ConceptNode(
                id="conditional",
                name="Conditional probability",
                definition="P(A given B).",
            ),
            ConceptNode(
                id="update", name="Bayesian update", definition="How evidence moves the prior."
            ),
        ],
        topo_order=["prior", "conditional", "update"],
        is_acyclic=True,
    )


class ScriptedModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._reply)


# ── the offline mapper ──────────────────────────────────────────────────────────────────────────


async def test_the_stub_mapper_credits_the_concepts_the_learner_named() -> None:
    """Deterministic and legible: a concept whose name the learner used in an answer is claimed;
    one they never mentioned is not. Enough for the offline path to place a learner past a root."""
    placed = await StubPriorMapper().map("Bayes' theorem", _EXCHANGES, _graph(), run_id="r1")

    by_id = {p.node_id: p.prior for p in placed.priors}
    assert by_id["prior"] >= 0.6
    assert by_id["conditional"] >= 0.6
    assert "update" not in by_id
    assert "medical" in placed.profile.lower()


async def test_the_stub_mapper_with_nothing_said_places_nobody() -> None:
    placed = await StubPriorMapper().map("Bayes' theorem", (), _graph(), run_id="r1")

    assert placed.priors == []
    assert placed.profile == ""


# ── the model-backed mapper ─────────────────────────────────────────────────────────────────────


async def test_the_mapper_reads_the_exchanges_and_the_map() -> None:
    model = ScriptedModel('{"profile": "A nurse reading test results.", "priors": []}')

    await ClaudePriorMapper("m", client=model).map(
        "Bayes' theorem", _EXCHANGES, _graph(), run_id="r1"
    )

    prompt = model.prompts[0]
    for exchange in _EXCHANGES:
        assert exchange.answer in prompt
    for node_id in ("prior", "conditional", "update"):
        assert node_id in prompt


async def test_the_mapper_returns_the_profile_and_priors_the_model_wrote() -> None:
    model = ScriptedModel(
        '{"profile": "A nurse reading test results.", '
        '"priors": [{"nodeId": "prior", "prior": 0.8}, {"nodeId": "conditional", "prior": 0.7}]}'
    )

    placed = await ClaudePriorMapper("m", client=model).map(
        "Bayes' theorem", _EXCHANGES, _graph(), run_id="r1"
    )

    assert placed.profile == "A nurse reading test results."
    assert [(p.node_id, p.prior) for p in placed.priors] == [("prior", 0.8), ("conditional", 0.7)]


async def test_a_prior_on_a_node_that_is_not_on_the_map_is_dropped_not_kept() -> None:
    """The mapper reasons; the map is the record. A node id the model invented would seed a claim
    about nothing, and the director would then try to verify a concept it cannot find."""
    model = ScriptedModel(
        '{"profile": "x", "priors": [{"nodeId": "made-up", "prior": 0.9}, '
        '{"nodeId": "prior", "prior": 1.4}, {"nodeId": "update", "prior": "high"}]}'
    )

    placed = await ClaudePriorMapper("m", client=model).map(
        "Bayes' theorem", _EXCHANGES, _graph(), run_id="r1"
    )

    # Unknown node dropped; an out-of-range number clamped to the most a claim may say (0.9, the
    # bound the prompt states and the code holds); a non-number dropped.
    assert [(p.node_id, p.prior) for p in placed.priors] == [("prior", 0.9)]


@pytest.mark.parametrize("reply", ["not json", "[]", '{"priors": "none"}'])
async def test_an_unusable_answer_is_a_failure_the_loop_can_degrade(reply: str) -> None:
    with pytest.raises(PriorMapperUnavailableError):
        await ClaudePriorMapper("m", client=ScriptedModel(reply)).map(
            "T", _EXCHANGES, _graph(), run_id="r1"
        )


async def test_a_mapper_that_hangs_is_bounded() -> None:
    class Hangs:
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(10)
            return AIMessage(content="{}")

    with pytest.raises(PriorMapperUnavailableError):
        await ClaudePriorMapper("m", client=Hangs(), deadline_s=0.05).map(
            "T", _EXCHANGES, _graph(), run_id="r1"
        )
