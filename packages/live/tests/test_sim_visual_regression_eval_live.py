"""A real false acceptance: correct readouts with a visibly open circuit."""

import json
import os
from pathlib import Path
from time import monotonic

import pytest
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.model_json import parse_json_object
from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.factory_prompts import factory_prompt
from lunaris_live.sims.schema.build_result import SimBuildResult
from lunaris_live.sims.schema.verified_bundle import VerifiedBundle
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
MODEL = os.getenv("LUNARIS_MODEL_STRONG", "claude-opus-4-8")
pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio(loop_scope="module"),
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


@pytest.mark.parametrize("artifact", ["rejected-open-circuit", "rejected-current-directions"])
async def test_publication_rejects_wrong_circuit_even_if_visual_critic_accepts(artifact, tmp_path):
    case = json.loads((Path(__file__).parent / "fixtures/sim_domains.json").read_text())[1]
    raw = ROOT / "documentation/evaluations/live-sim-domains-2026-09-12" / f"{artifact}.json"
    rejected = SimBuildResult.model_validate_json(raw.read_text())
    state = {
        "node": ConceptNode.model_validate(case["node"]),
        "criterion": MasteryCriterion.model_validate(case["criterion"]),
        "spec": rejected.spec,
        "candidate": rejected.bundle.candidate,
    }
    scope = CostScope(
        run_id="p3-open-circuit-regression",
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id="evaluation",
        price_book=PriceBook.current(),
    )
    started = monotonic()
    with cost_scope(scope):
        reply = await ClaudeSimModel(MODEL).complete(
            factory_prompt(state, stage="review"),
            max_tokens=1500,
            images=rejected.reports[-1].screenshots,
        )
    verdict = parse_json_object(reply.text)
    structural = await ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    ).verify(rejected.bundle.candidate, rejected.spec)
    (tmp_path / "review.json").write_text(
        json.dumps(
            {
                "verdict": verdict,
                "structuralVerification": structural.model_dump(by_alias=True),
                "rawResponse": reply.text,
                "costUsd": reply.cost_usd,
                "inputTokens": reply.input_tokens,
                "outputTokens": reply.output_tokens,
                "elapsedMs": int((monotonic() - started) * 1000),
            },
            indent=2,
        )
    )
    assert not structural.approved
    assert "assembled circuit" in " ".join(structural.reasons)

    with pytest.raises(ValidationError, match="Only the exact independently verified bundle"):
        VerifiedBundle(
            candidate=rejected.bundle.candidate,
            spec=rejected.spec,
            report=structural,
            visual_verdict=rejected.bundle.visual_verdict,
        )
