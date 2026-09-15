"""Real compiler orchestration grounds both passes and independently verifies source coverage."""

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.corpus.schemas.provenance import CorpusProvenance
from lunaris_live.corpus.schemas.section import CorpusSection
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.graph import ClaudeGraphCompiler


class _Model:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=json.dumps(self.responses.pop(0)))


def _source() -> CorpusSnapshot:
    return CorpusSnapshot(
        source=CorpusProvenance(course_id="course", title="Consent", digest="a" * 64, run_id="r"),
        sections=(
            CorpusSection(
                locator="lesson:one",
                kind="lesson",
                text="Consent identifies the purpose.",
                answer_key="PRIVATE_EXAM_KEY",
            ),
        ),
    )


def _decomposition() -> dict[str, Any]:
    return {
        "concepts": [
            {
                "id": "consent",
                "name": "Consent",
                "definition": "Consent identifies the purpose.",
                "requires": [],
            }
        ]
    }


def _spec() -> dict[str, Any]:
    return {
        "objective": "Explain consent",
        "misconceptions": [],
        "depth": "applied",
        "criteria": [{"kind": "explain", "statement": "Explain the purpose"}],
    }


def _verification() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "nodeId": "consent",
                "classification": "source",
                "evidence": [{"locator": "lesson:one", "quote": "Consent identifies the purpose."}],
                "rationale": "The source explains the concept.",
                "supported": True,
            }
        ]
    }


async def test_grounding_reaches_both_passes_and_independent_verifier_without_answer_keys() -> None:
    model = _Model([_decomposition(), _spec(), _verification()])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=_source()
    )
    assert len(model.prompts) == 3
    assert all("lesson:one" in prompt for prompt in model.prompts)
    assert all("PRIVATE_EXAM_KEY" not in prompt for prompt in model.prompts)
    assert graph.grounding_report.status == "passed"
    assert graph.grounding_report.nodes[0].locators == ("lesson:one",)
    assert graph.grounding_report.source_digest == "a" * 64
    assert graph.corpus.status == "pending"
    assert "PRIVATE_EXAM_KEY" not in graph.model_dump_json()


@pytest.mark.parametrize(
    "variant", ["invented_quote", "invented_locator", "unsupported", "missing_node"]
)
async def test_independent_bad_evidence_never_passes(variant: str) -> None:
    verdict = _verification()
    if variant == "invented_quote":
        verdict["nodes"][0]["evidence"][0]["quote"] = "Unrelated claim"
    elif variant == "invented_locator":
        verdict["nodes"][0]["evidence"][0]["locator"] = "lesson:invented"
    elif variant == "unsupported":
        verdict["nodes"][0]["supported"] = False
    else:
        verdict["nodes"] = []
    model = _Model([_decomposition(), _spec(), verdict])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=_source()
    )
    assert graph.grounding_report.status == "failed"
    assert graph.corpus.status == "pending"


async def test_extension_preserves_source_and_marks_new_material_unverified() -> None:
    model = _Model(
        [
            _decomposition(),
            _spec(),
            _verification(),
            {
                "concepts": [
                    {
                        "id": "new",
                        "name": "New",
                        "definition": "Beyond source",
                        "requires": ["consent"],
                    }
                ]
            },
            _spec(),
        ]
    )
    compiler = ClaudeGraphCompiler("fixture", client=model)
    graph = await compiler.compile("Consent", graph_id="g", run_id="r", grounding=_source())
    extended = await compiler.extend(graph, request="New", anchors=["consent"], run_id="next")
    assert extended.corpus == graph.corpus
    assert extended.nodes[0] == graph.nodes[0]
    assert extended.grounding_report.status == "failed"
    assert extended.grounding_report.nodes[-1].classification == "unsupported"
    assert "extension_unverified" in extended.grounding_report.issues


async def test_context_omission_is_explicit_and_never_verified() -> None:
    snapshot = _source().model_copy(
        update={
            "sections": tuple(
                CorpusSection(
                    locator=f"lesson:{index}",
                    kind="lesson",
                    text="Consent identifies the purpose." + "x" * 19000,
                )
                for index in range(3)
            )
        }
    )
    verdict = _verification()
    verdict["nodes"][0]["evidence"][0]["locator"] = "lesson:0"
    model = _Model([_decomposition(), _spec(), verdict])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=snapshot
    )
    assert graph.grounding_report.omitted_locators == ("lesson:1", "lesson:2")
    assert graph.grounding_report.status == "failed"
    assert all(len(prompt) < 36000 for prompt in model.prompts)


async def test_corpus_authoring_call_count_is_capped() -> None:
    concepts = [
        {
            "id": f"n{i}",
            "name": f"Node {i}",
            "definition": "Consent identifies the purpose.",
            "requires": [],
        }
        for i in range(25)
    ]
    model = _Model([{"concepts": concepts}, *[_spec()] * 20, {"nodes": []}])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=_source()
    )
    assert len(graph.nodes) == 20
    assert len(model.prompts) == 22
    assert graph.grounding_report.status == "failed"


@pytest.mark.parametrize("linked", [True, False])
@pytest.mark.parametrize("supported", [True, False])
async def test_prerequisite_exception_requires_an_actual_dependency(
    linked: bool, supported: bool
) -> None:
    decomposition = _decomposition()
    decomposition["concepts"][0]["requires"] = ["background"] if linked else []
    decomposition["concepts"].append(
        {
            "id": "background",
            "name": "Background",
            "definition": "Necessary background",
            "requires": [],
        }
    )
    verdict = _verification()
    verdict["nodes"].append(
        {
            "nodeId": "background",
            "classification": "prerequisite",
            "supported": supported,
            "evidence": [],
            "rationale": "Required background to understand consent.",
        }
    )
    model = _Model([decomposition, _spec(), _spec(), verdict])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=_source()
    )
    assert graph.grounding_report.status == ("passed" if linked and supported else "failed")
    report = next(node for node in graph.grounding_report.nodes if node.node_id == "background")
    assert report.classification == ("prerequisite" if linked and supported else "unsupported")
    assert report.locators == ()


async def test_verification_is_inside_compile_deadline() -> None:
    import asyncio

    class SlowVerifier(_Model):
        async def ainvoke(self, prompt: str) -> AIMessage:
            if len(self.prompts) == 2:
                await asyncio.Event().wait()
            return await super().ainvoke(prompt)

    model = SlowVerifier([_decomposition(), _spec(), _verification()])
    with pytest.raises(TimeoutError):
        await ClaudeGraphCompiler("fixture", client=model, deadline_s=0.01).compile(
            "Consent", graph_id="g", run_id="r", grounding=_source()
        )


async def test_oversized_authored_graph_skips_verification_call_and_fails_closed() -> None:
    spec = _spec()
    spec["misconceptions"] = ["wrong model " * 50] * 200
    model = _Model([_decomposition(), spec, _verification()])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=_source()
    )
    assert len(model.prompts) == 2
    assert graph.grounding_report.status == "failed"
    assert "verification_input_limit" in graph.grounding_report.issues


async def test_corpus_extension_is_bounded_and_preserves_source_coverage() -> None:
    additions = {
        "concepts": [
            {
                "id": f"extra{i}",
                "name": f"Extra {i}",
                "definition": "Outside source",
                "requires": ["consent"],
            }
            for i in range(25)
        ]
    }
    model = _Model([_decomposition(), _spec(), _verification(), additions, *[_spec()] * 5])
    compiler = ClaudeGraphCompiler("fixture", client=model)
    graph = await compiler.compile("Consent", graph_id="g", run_id="r", grounding=_source())
    extended = await compiler.extend(
        graph, request="Beyond source", anchors=["consent"], run_id="next"
    )
    assert len(extended.nodes) == 6
    assert len(model.prompts) == 9
    assert extended.grounding_report.nodes[0] == graph.grounding_report.nodes[0]
    assert all(node.classification == "unsupported" for node in extended.grounding_report.nodes[1:])


async def test_uncovered_source_material_is_reported_even_when_nodes_are_supported() -> None:
    source = _source()
    source = source.model_copy(
        update={
            "sections": (
                *source.sections,
                CorpusSection(
                    locator="lesson:uncovered",
                    kind="lesson",
                    text="Additional unaddressed material.",
                ),
            )
        }
    )
    model = _Model([_decomposition(), _spec(), _verification()])
    graph = await ClaudeGraphCompiler("fixture", client=model).compile(
        "Consent", graph_id="g", run_id="r", grounding=source
    )
    assert graph.grounding_report.nodes[0].classification == "source"
    assert graph.grounding_report.uncovered_locators == ("lesson:uncovered",)
    assert graph.grounding_report.status == "failed"
