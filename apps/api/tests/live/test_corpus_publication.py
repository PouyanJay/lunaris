"""Source mapping must finish before a graph becomes visible or usable."""

import asyncio
from typing import TYPE_CHECKING, Literal

import pytest
from _auth import USER_A
from lunaris_api.live.service import LiveGraphService
from lunaris_live.corpus.mapping.models.request import MappingRequest
from lunaris_live.corpus.schemas.grounding_report import GroundingReport, NodeGrounding
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.video.schemas.inventory import VideoInventory
from lunaris_live.graph import (
    ConceptGraph,
    ICompileProgressSink,
    MemoryGraphStore,
    StubGraphCompiler,
)
from test_live_corpus_skeleton import COURSE_ID, DIGEST, FixtureResolver

if TYPE_CHECKING:
    from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot


class GroundedCompiler(StubGraphCompiler):
    async def compile(
        self,
        topic: str,
        *,
        graph_id: str,
        run_id: str,
        on_progress: ICompileProgressSink | None = None,
        grounding: "CorpusSnapshot | None" = None,
    ) -> ConceptGraph:
        graph = await super().compile(
            topic, graph_id=graph_id, run_id=run_id, on_progress=on_progress, grounding=grounding
        )
        graph.grounding_report = GroundingReport(
            source_digest=DIGEST,
            run_id=run_id,
            status="passed",
            nodes=tuple(
                NodeGrounding(node_id=node.id, classification="source", locators=("lesson:1",))
                for node in graph.nodes
            ),
        )
        return graph


class RecordingStore(MemoryGraphStore):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[ConceptGraph] = []

    def save(
        self,
        graph: ConceptGraph,
        *,
        owner_id: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        self.writes.append(graph.model_copy(deep=True))
        super().save(graph, owner_id=owner_id, expected_version=expected_version)


class WaitingPreparer:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    async def prepare(
        self, graph: ConceptGraph, *, snapshot: "CorpusSnapshot", owner_id: str
    ) -> ConceptGraph:
        assert owner_id == USER_A
        assert snapshot.source.digest == DIGEST
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True
        return graph


async def test_no_graph_published_while_mapping_is_pending_or_cancelled() -> None:
    store = RecordingStore()
    preparer = WaitingPreparer()
    service = LiveGraphService(
        GroundedCompiler(), store, corpus_resolver=FixtureResolver(), corpus_preparer=preparer
    )
    task = asyncio.create_task(
        service.compile(
            "Patient data",
            run_id="mapping-run",
            owner_id=USER_A,
            corpus=CorpusReference(course_id=COURSE_ID),
        )
    )
    try:
        await asyncio.wait_for(preparer.entered.wait(), timeout=1)
        assert store.writes == []
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert preparer.cancelled
    assert store.writes == []


async def test_corpus_deadline_cancels_mapping_and_never_publishes() -> None:
    store = RecordingStore()
    preparer = WaitingPreparer()
    service = LiveGraphService(
        GroundedCompiler(),
        store,
        corpus_resolver=FixtureResolver(),
        corpus_preparer=preparer,
        corpus_deadline_s=0.05,
    )
    with pytest.raises(TimeoutError):
        await service.compile(
            "Patient data",
            run_id="deadline-run",
            owner_id=USER_A,
            corpus=CorpusReference(course_id=COURSE_ID),
        )
    assert preparer.entered.is_set()
    assert preparer.cancelled
    assert store.writes == []


class EmptyInventory:
    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        from lunaris_live.corpus.video.schemas.inventory import VideoInventory

        assert (course_id, owner_id) == (COURSE_ID, USER_A)
        return VideoInventory()


class CompletingMapper:
    def __init__(
        self,
        *,
        digest: str = DIGEST,
        status: Literal["passed", "failed"] = "passed",
        decisions: bool = True,
    ) -> None:
        self.digest = digest
        self.status = status
        self.decisions = decisions

    async def map(self, request: MappingRequest) -> ConceptGraph:
        from lunaris_live.corpus.mapping.schemas.report import MappingDecision, MappingReport
        from lunaris_live.corpus.schemas.asset import NodeAsset
        from lunaris_live.corpus.schemas.asset_verification import AssetVerification

        nodes = [
            node.model_copy(
                update={
                    "assets": [
                        NodeAsset(
                            asset_id="material-" + node.id,
                            kind="lesson",
                            origin="ingested",
                            locator="lesson:1",
                            source_digest=DIGEST,
                            excerpt=request.snapshot.sections[0].text,
                            verification=AssetVerification(
                                source_digest=DIGEST,
                                run_id=request.run_id,
                                verifier_version="mapping-verifier-v1",
                            ),
                        )
                    ]
                }
            )
            for node in request.graph.nodes
        ]
        return request.graph.model_copy(
            update={
                "nodes": nodes,
                "mapping_report": MappingReport(
                    source_digest=self.digest,
                    run_id=request.run_id,
                    status=self.status,
                    mappings=tuple(
                        MappingDecision(
                            node_id=n.id, locator="lesson:1", status="approved", reason="verified"
                        )
                        for n in nodes
                    )
                    if self.decisions
                    else (),
                ),
            }
        )


@pytest.mark.parametrize(
    "digest,status,expected",
    [
        (DIGEST, "passed", "verified"),
        ("b" * 64, "passed", "failed"),
        (DIGEST, "failed", "failed"),
    ],
)
async def test_only_consistent_verified_mapping_is_published_once(
    digest: str, status: Literal["passed", "failed"], expected: str
) -> None:
    from lunaris_api.live.corpus.preparer import CorpusGraphPreparer

    store = RecordingStore()
    service = LiveGraphService(
        GroundedCompiler(),
        store,
        corpus_resolver=FixtureResolver(),
        corpus_preparer=CorpusGraphPreparer(
            CompletingMapper(digest=digest, status=status), EmptyInventory()
        ),
    )
    result = await service.compile(
        "Patient data",
        run_id="publish-run",
        owner_id=USER_A,
        corpus=CorpusReference(course_id=COURSE_ID),
    )
    assert result.corpus.status == expected
    assert len(store.writes) == 1
    assert store.writes[0].corpus.status == expected
    assert store.load(result.graph_id, owner_id=USER_A) == result


async def test_approved_assets_missing_from_verifier_report_cannot_publish_ready() -> None:
    from lunaris_api.live.corpus.preparer import CorpusGraphPreparer

    store = RecordingStore()
    service = LiveGraphService(
        GroundedCompiler(),
        store,
        corpus_resolver=FixtureResolver(),
        corpus_preparer=CorpusGraphPreparer(CompletingMapper(decisions=False), EmptyInventory()),
    )
    result = await service.compile(
        "Patient data",
        run_id="no-decisions",
        owner_id=USER_A,
        corpus=CorpusReference(course_id=COURSE_ID),
    )
    assert result.corpus is not None
    assert result.corpus.status == "failed"


class EditedResolver(FixtureResolver):
    def __init__(self) -> None:
        self.reads = 0

    async def resolve(
        self, reference: CorpusReference, *, owner_id: str, run_id: str
    ) -> "CorpusSnapshot":
        self.reads += 1
        snapshot = await super().resolve(reference, owner_id=owner_id, run_id=run_id)
        if self.reads > 1:
            return snapshot.model_copy(
                update={"source": snapshot.source.model_copy(update={"digest": "c" * 64})}
            )
        return snapshot


async def test_source_edit_during_mapping_prevents_publication() -> None:
    from lunaris_api.live.corpus.invalid import CorpusInvalidError
    from lunaris_api.live.corpus.preparer import CorpusGraphPreparer

    store = RecordingStore()
    service = LiveGraphService(
        GroundedCompiler(),
        store,
        corpus_resolver=EditedResolver(),
        corpus_preparer=CorpusGraphPreparer(CompletingMapper(), EmptyInventory()),
    )
    with pytest.raises(CorpusInvalidError):
        await service.compile(
            "Patient data",
            run_id="source-edited",
            owner_id=USER_A,
            corpus=CorpusReference(course_id=COURSE_ID),
        )
    assert store.writes == []
