"""Separate model proposal/verification can attach only actual source material."""

import json
from types import SimpleNamespace

import pytest
from lunaris_live.corpus.mapping.asset_mapper import AssetMapper
from lunaris_live.corpus.mapping.models.request import MappingRequest
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.corpus.video.schemas.inventory import VideoInventory
from lunaris_live.graph.schema import ConceptGraph


def request() -> MappingRequest:
    snapshot = CorpusSnapshot.model_validate(
        {
            "source": {
                "courseId": "course1",
                "title": "Records",
                "digest": "a" * 64,
                "runId": "compile",
            },
            "sections": [
                {"locator": "lesson:1", "kind": "lesson", "text": "A record stores patient data."},
                {
                    "locator": "assessment:1",
                    "kind": "assessment",
                    "text": "What does a record store?",
                    "answerKey": "PRIVATE ANSWER",
                },
            ],
        }
    )
    graph = ConceptGraph.model_validate(
        {
            "graphId": "g1",
            "topic": "Records",
            "corpus": snapshot.source.model_dump(),
            "nodes": [
                {"id": "n1", "name": "Record", "definition": "A record stores patient data."}
            ],
            "groundingReport": {
                "sourceDigest": "a" * 64,
                "runId": "compile",
                "status": "passed",
                "nodes": [{"nodeId": "n1", "classification": "source", "locators": ["lesson:1"]}],
            },
        }
    )
    return MappingRequest(graph, snapshot, VideoInventory(), "map-run")


class Model:
    def __init__(self, replies: list[dict[str, object]]) -> None:
        self.replies = iter(replies)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content=json.dumps(next(self.replies)))


def proposal(locator: str = "lesson:1") -> dict[str, object]:
    return {"mappings": [{"nodeId": "n1", "locator": locator}]}


def verdict(
    approved: bool = True, quote: str = "A record stores patient data."
) -> dict[str, object]:
    return {
        "mappings": [
            {"nodeId": "n1", "locator": "lesson:1", "approved": approved, "evidence": [quote]}
        ]
    }


async def test_independent_verification_builds_exact_source_assets_without_keys() -> None:
    model = Model([proposal(), verdict()])
    mapped = await AssetMapper("fixture", client=model).map(request())
    assert len(model.prompts) == 2
    assert "Independently verify" in model.prompts[1]
    assert "PRIVATE ANSWER" not in "".join(model.prompts) + mapped.model_dump_json()
    assert mapped.mapping_report.status == "passed"
    asset = mapped.nodes[0].assets[0]
    assert asset.excerpt == "A record stores patient data."
    assert asset.source_digest == "a" * 64
    assert asset.verification.run_id == "map-run"
    assert mapped.corpus.status == "pending"


@pytest.mark.parametrize(
    "approved,quote", [(False, "A record stores patient data."), (True, "Invented statement")]
)
async def test_wrong_or_unverifiable_mapping_cannot_publish_assets(
    approved: bool, quote: str
) -> None:
    mapped = await AssetMapper("fixture", client=Model([proposal(), verdict(approved, quote)])).map(
        request()
    )
    assert mapped.nodes[0].assets == []
    assert mapped.mapping_report.status == "failed"


async def test_fabricated_locator_never_approved_by_matching_model_claim() -> None:
    model = Model(
        [
            proposal("invented:source"),
            {
                "mappings": [
                    {
                        "nodeId": "n1",
                        "locator": "invented:source",
                        "approved": True,
                        "evidence": ["Fabricated"],
                    }
                ]
            },
        ]
    )
    mapped = await AssetMapper("fixture", client=model).map(request())
    assert mapped.nodes[0].assets == []
    assert mapped.mapping_report.status == "failed"


async def test_stale_grounding_rejected_before_model_call() -> None:
    current = request()
    graph = current.graph.model_copy(
        update={
            "grounding_report": current.graph.grounding_report.model_copy(
                update={"source_digest": "b" * 64}
            )
        }
    )
    model = Model([])
    mapped = await AssetMapper("fixture", client=model).map(
        MappingRequest(graph, current.snapshot, current.inventory, "run")
    )
    assert model.prompts == []
    assert mapped.mapping_report.status == "failed"


async def test_question_only_mapping_remains_practice_and_is_not_enough_to_publish() -> None:
    model = Model(
        [
            proposal("assessment:1"),
            {
                "mappings": [
                    {
                        "nodeId": "n1",
                        "locator": "assessment:1",
                        "approved": True,
                        "evidence": ["What does a record store?"],
                    }
                ]
            },
        ]
    )
    mapped = await AssetMapper("fixture", client=model).map(request())
    assert mapped.mapping_report.status == "failed"
    assert mapped.nodes[0].assets[0].excerpt == "What does a record store?"
    assert any(gap.reason == "node_without_material" for gap in mapped.mapping_report.gaps)
    assert "PRIVATE ANSWER" not in "".join(model.prompts) + mapped.model_dump_json()


async def test_video_retains_exact_clip_bounds_and_separate_media_digest() -> None:
    current = request()
    inventory = VideoInventory.model_validate(
        {
            "clips": [
                {
                    "jobId": "j1",
                    "sourceDigest": "b" * 64,
                    "locator": "video:j1:" + "b" * 64 + ":0:0",
                    "startS": 3,
                    "endS": 5,
                    "durationS": 7,
                    "title": "Records",
                    "transcript": [
                        {"startS": 3, "endS": 5, "text": "A record stores patient data."}
                    ],
                }
            ]
        }
    )
    locator = inventory.clips[0].locator
    model = Model(
        [
            proposal(locator),
            {
                "mappings": [
                    {
                        "nodeId": "n1",
                        "locator": locator,
                        "approved": True,
                        "evidence": ["A record stores patient data."],
                    }
                ]
            },
        ]
    )
    mapped = await AssetMapper("fixture", client=model).map(
        MappingRequest(current.graph, current.snapshot, inventory, "r")
    )
    asset = mapped.nodes[0].assets[0]
    assert mapped.mapping_report.status == "passed"
    assert asset.clip == inventory.clips[0]
    assert asset.source_digest == "a" * 64
    assert asset.clip.source_digest == "b" * 64


async def test_partial_supported_node_coverage_blocks_readiness() -> None:
    current = request()
    graph = current.graph.model_copy(
        update={
            "nodes": [*current.graph.nodes, current.graph.nodes[0].model_copy(update={"id": "n2"})],
            "grounding_report": current.graph.grounding_report.model_copy(
                update={
                    "nodes": (
                        *current.graph.grounding_report.nodes,
                        current.graph.grounding_report.nodes[0].model_copy(
                            update={"node_id": "n2"}
                        ),
                    )
                }
            ),
        }
    )
    mapped = await AssetMapper("fixture", client=Model([proposal(), verdict()])).map(
        MappingRequest(graph, current.snapshot, current.inventory, "r")
    )
    assert mapped.mapping_report.status == "failed"
    assert any(
        gap.node_id == "n2" and gap.reason == "node_without_material"
        for gap in mapped.mapping_report.gaps
    )


@pytest.mark.parametrize("extra", [True, False])
async def test_duplicate_or_missing_verdicts_fail_closed(extra: bool) -> None:
    payload = verdict()
    payload["mappings"] = payload["mappings"] * 2 if extra else []
    mapped = await AssetMapper("fixture", client=Model([proposal(), payload])).map(request())
    assert not mapped.nodes[0].assets
    assert mapped.mapping_report.status == "failed"


async def test_uncertain_provider_failure_is_not_retried() -> None:
    class FailedModel:
        calls = 0

        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            self.calls += 1
            raise RuntimeError("private provider diagnostic")

    model = FailedModel()
    mapped = await AssetMapper("fixture", client=model).map(request())
    assert model.calls == 1
    assert mapped.mapping_report.status == "failed"
    assert "private provider diagnostic" not in mapped.model_dump_json()


async def test_cancellation_propagates_and_cancels_provider() -> None:
    import asyncio

    started, stopped = asyncio.Event(), asyncio.Event()

    class WaitingModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            raise AssertionError("unreachable")

    task = asyncio.create_task(AssetMapper("fixture", client=WaitingModel()).map(request()))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


async def test_deadline_fails_without_second_provider_attempt() -> None:
    import asyncio

    class SlowModel:
        calls = 0

        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            self.calls += 1
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    model = SlowModel()
    mapped = await AssetMapper("fixture", client=model, deadline_s=0.01).map(request())
    assert mapped.mapping_report.status == "failed"
    assert model.calls == 1


async def test_failed_remap_does_not_leave_previously_verified_source_ready() -> None:
    current = request()
    graph = current.graph.model_copy(
        update={"corpus": current.graph.corpus.model_copy(update={"status": "verified"})}
    )
    mapped = await AssetMapper("fixture", client=Model([proposal(), verdict(False)])).map(
        MappingRequest(graph, current.snapshot, current.inventory, "r")
    )
    assert mapped.corpus.status == "pending"


async def test_model_construction_occurs_in_each_current_tenant_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextvars import ContextVar

    tenant = ContextVar("mapping_test_tenant", default="none")
    built: list[str] = []

    class ScopedModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(
                content=json.dumps(verdict() if "Independently verify" in prompt else proposal())
            )

    def build(model_id: str, **kwargs: object) -> ScopedModel:
        assert kwargs["max_retries"] == 0
        built.append(tenant.get())
        return ScopedModel()

    monkeypatch.setattr("lunaris_live.corpus.mapping.asset_mapper.build_chat_model", build)
    mapper = AssetMapper("fixture")
    for owner in ("first", "second"):
        token = tenant.set(owner)
        try:
            assert (await mapper.map(request())).mapping_report.status == "passed"
        finally:
            tenant.reset(token)
    assert built == ["first", "first", "second", "second"]


async def test_unsupported_node_is_never_a_mapping_target() -> None:
    current = request()
    report = current.graph.grounding_report.model_copy(
        update={
            "nodes": (
                current.graph.grounding_report.nodes[0].model_copy(
                    update={"classification": "unsupported"}
                ),
            )
        }
    )
    graph = current.graph.model_copy(update={"grounding_report": report})
    model = Model([])
    mapped = await AssetMapper("fixture", client=model).map(
        MappingRequest(graph, current.snapshot, current.inventory, "r")
    )
    assert not model.prompts
    assert mapped.mapping_report.status == "failed"


async def test_candidate_budget_records_gap_and_keeps_bounded_model_context() -> None:
    current = request()
    sections = (
        *current.snapshot.sections,
        *(
            current.snapshot.sections[0].model_copy(update={"locator": f"lesson:{i}"})
            for i in range(2, 100)
        ),
    )
    snapshot = current.snapshot.model_copy(update={"sections": sections})
    model = Model([proposal(), verdict()])
    mapped = await AssetMapper("fixture", client=model).map(
        MappingRequest(current.graph, snapshot, current.inventory, "r")
    )
    assert mapped.mapping_report.status == "passed"
    assert any(gap.reason == "candidate_limit" for gap in mapped.mapping_report.gaps)
    assert all(len(prompt) <= 128000 for prompt in model.prompts)


async def test_missing_optional_video_remains_an_explicit_nonblocking_gap() -> None:
    current = request()
    inventory = VideoInventory.model_validate({"gaps": [{"reason": "silent"}]})
    mapped = await AssetMapper("fixture", client=Model([proposal(), verdict()])).map(
        MappingRequest(current.graph, current.snapshot, inventory, "r")
    )
    assert mapped.mapping_report.status == "passed"
    assert any(gap.reason == "video_unavailable" for gap in mapped.mapping_report.gaps)
