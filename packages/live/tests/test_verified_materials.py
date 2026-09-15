from collections.abc import AsyncIterator

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from lunaris_live.corpus.schemas.asset import NodeAsset
from lunaris_live.graph import ConceptGraph, ConceptNode
from lunaris_live.session import (
    ClaudeTutor,
    DirectorMove,
    LearnerModel,
    MoveKind,
    SessionClock,
    open_session,
)
from test_open_session import SpyTutor


def _asset(*, verified: bool = True) -> NodeAsset:
    return NodeAsset(
        asset_id="asset-a",
        kind="lesson",
        origin="ingested",
        locator="lesson:1",
        source_digest="a" * 64,
        title="Course lesson",
        excerpt="A privacy rule governs record access.",
        source_label="Source course",
        verification={"run_id": "verify-run", "verifier_version": "v1", "source_digest": "a" * 64}
        if verified
        else None,
    )


class RecordingModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content='{"hint":"Think about access."}')

    async def astream(self, prompt: str) -> AsyncIterator[AIMessageChunk]:
        self.prompts.append(prompt)
        yield AIMessageChunk(content="Consider who can access the record.")


@pytest.mark.parametrize("kind", [MoveKind.INTRODUCE, MoveKind.RETRIEVE])
async def test_all_tutor_paths_use_verified_material_only_outside_retrieval(kind: MoveKind) -> None:
    model = RecordingModel()
    tutor = ClaudeTutor("fixture", client=model)
    node = ConceptNode(id="a", name="Privacy", definition="A rule for access.", assets=[_asset()])
    move = DirectorMove(kind=kind, node_id="a", reason="Test source support")
    await tutor.teach(move, node, topic="Privacy", run_id="r")
    assert "".join([chunk async for chunk in tutor.stream(move, node, topic="Privacy", run_id="r")])
    await tutor.illustrate(move, node, topic="Privacy", run_id="r")
    assert len(model.prompts) == 3
    for prompt in model.prompts:
        assert ("A privacy rule governs record access." in prompt) == (kind is MoveKind.INTRODUCE)


async def test_session_persists_only_verified_support_without_mastery_credit() -> None:
    verified = _asset()
    rejected = _asset(verified=False)
    graph = ConceptGraph(
        graph_id="g",
        topic="Privacy",
        nodes=[
            ConceptNode(
                id="a", name="Privacy", definition="Access rules.", assets=[verified, rejected]
            )
        ],
        topo_order=["a"],
        is_acyclic=True,
    )
    model = LearnerModel(graph_id="g")
    tutor = SpyTutor()
    outcome = await open_session(
        graph,
        model,
        SessionClock(turn=1, elapsed_s=0, budget_s=1800),
        session_id="s",
        run_id="r",
        tutor=tutor,
    )
    assert tutor.calls[0][1].assets == [verified]
    assert outcome.session.turns[0].materials == [verified]
    assert outcome.model == model


@pytest.mark.parametrize("kind", list(MoveKind))
async def test_material_admission_rejects_unverified_and_mismatched_assets(
    kind: MoveKind,
) -> None:
    from lunaris_live.session.supporting_assets import supporting_assets

    accepted = _asset()
    mismatched = accepted.model_copy(update={"source_digest": "b" * 64})
    assessment = accepted.model_copy(update={"kind": "assessment"})
    node = ConceptNode(
        id="a",
        name="Privacy",
        definition="Access rules.",
        assets=[_asset(verified=False), mismatched, assessment, accepted],
    )
    assert supporting_assets(node, kind) == (
        [] if kind is MoveKind.RETRIEVE else [assessment, accepted]
    )


async def test_imported_practice_prompt_is_recorded_without_grading_or_tutor_answer_context() -> (
    None
):
    from lunaris_live.session.material_notes import material_notes

    practice = _asset().model_copy(
        update={"kind": "assessment", "excerpt": "Who may access this record?"}
    )
    node = ConceptNode(id="a", name="Privacy", definition="Access rules.", assets=[practice])
    graph = ConceptGraph(
        graph_id="g", topic="Privacy", nodes=[node], topo_order=["a"], is_acyclic=True
    )
    model = LearnerModel(graph_id="g")
    outcome = await open_session(
        graph,
        model,
        SessionClock(turn=1, elapsed_s=0, budget_s=1800),
        session_id="s",
        run_id="practice-run",
        tutor=SpyTutor(),
    )
    assert outcome.session.turns[0].materials == [practice]
    assert outcome.model == model
    assert material_notes(node, MoveKind.INTRODUCE) == ""


async def test_verified_video_material_preserves_original_clip_evidence_on_turn() -> None:
    from lunaris_live.session.schema.session_turn import SessionTurn

    clip = {
        "job_id": "video-job",
        "source_digest": "b" * 64,
        "locator": "video:video-job:" + "b" * 64 + ":0:0",
        "start_s": 2,
        "end_s": 7,
        "duration_s": 10,
        "title": "Access example",
        "transcript": [{"start_s": 2, "end_s": 7, "text": "Only authorized staff may read it."}],
    }
    payload = _asset().model_dump()
    payload.update(kind="video_clip", locator=clip["locator"], clip=clip)
    asset = NodeAsset.model_validate(payload)
    graph = ConceptGraph(
        graph_id="g",
        topic="Privacy",
        nodes=[ConceptNode(id="a", name="Privacy", definition="Access rules.", assets=[asset])],
        topo_order=["a"],
        is_acyclic=True,
    )
    model = LearnerModel(graph_id="g")
    outcome = await open_session(
        graph,
        model,
        SessionClock(turn=1, elapsed_s=0, budget_s=1800),
        session_id="s",
        run_id="clip-run",
        tutor=SpyTutor(),
    )
    recorded = SessionTurn.model_validate_json(outcome.session.turns[0].model_dump_json())
    assert recorded.materials[0].clip is not None
    assert recorded.materials[0].clip.model_dump() == asset.clip.model_dump()
    assert outcome.model == model


async def test_due_retrieval_does_not_reuse_answer_revealing_prefetched_lesson() -> None:
    from datetime import UTC, datetime, timedelta

    from lunaris_live.session import LessonParts, NodeKnowledge

    now = datetime.now(UTC)
    graph = ConceptGraph(
        graph_id="g",
        topic="Privacy",
        nodes=[ConceptNode(id="a", name="Privacy", definition="Access rules.", assets=[_asset()])],
        topo_order=["a"],
        is_acyclic=True,
    )
    model = LearnerModel(
        graph_id="g",
        nodes={
            "a": NodeKnowledge(
                node_id="a", estimate=0.6, evidence_count=1, due_at=now - timedelta(days=1)
            )
        },
    )
    outcome = await open_session(
        graph,
        model,
        SessionClock(turn=1, elapsed_s=0, budget_s=1800, at=now),
        session_id="s",
        run_id="retrieval-source-run",
        tutor=SpyTutor(),
        prefetched={"a": LessonParts(hint="Secret source answer should not appear.")},
    )
    assert outcome.session.turns[0].move.kind is MoveKind.RETRIEVE
    assert "Secret source answer" not in outcome.session.model_dump_json()
    assert outcome.consumed_material is None
    assert outcome.session.turns[0].materials == []
