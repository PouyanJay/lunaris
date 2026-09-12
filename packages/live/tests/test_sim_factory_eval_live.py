"""Bounded real-provider evidence; inspect result.json and the verifier's PNGs in tmp_path.

    uv run --env-file .env pytest packages/live/tests/test_sim_factory_eval_live.py \
        -m eval --basetemp /tmp/lunaris-sim-eval -q

Build the appliance described in infra/sim-verifier/README.md first. This evaluates generation,
not production session delivery or the learner acceptance gate.
"""

import os
from pathlib import Path

import pytest
from lunaris_live.graph.schema import ConceptNode, MasteryCriterion
from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.factory import SimFactory
from lunaris_live.sims.schema.build_budget import SimBuildBudget
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]
ROOT = Path(__file__).resolve().parents[3]


async def test_real_provider_builds_inspectable_verified_simulator(tmp_path):
    node = ConceptNode(
        id="linear-smoke",
        name="Linear relationship",
        definition="For y = 2x, each increase of x by 1 increases y by 2. "
        "Over x from 0 to 10, y ranges from 0 to 20.",
    )
    criterion = MasteryCriterion(
        kind="manipulate",
        statement="Compare how y changes when x changes in y = 2x.",
        needs_sim=True,
    )
    factory = SimFactory(
        ClaudeSimModel("claude-sonnet-4-6"),
        ContainerSimVerifier(
            image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
        ),
        budget=SimBuildBudget(
            attempts=3, output_tokens=8000, deadline_s=240, token_reservation=100000
        ),
    )
    scope = CostScope(
        run_id="p3-builder-smoke",
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id=node.id,
        price_book=PriceBook.current(),
    )
    with cost_scope(scope):
        result = await factory.build(node, criterion, run_id=scope.run_id)
    (tmp_path / "result.json").write_text(result.model_dump_json(by_alias=True, indent=2))
    assert result.status == "approved", result.reason
    assert result.bundle.visual_verdict.passed
    assert len(result.bundle.report.screenshots) == 2
    assert all(call.cost_usd is not None for call in result.calls)
