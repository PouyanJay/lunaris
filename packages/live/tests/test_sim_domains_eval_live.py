"""Paid domain evaluations with fixed, independently calculated behavior checks."""

import base64
import json
import os
from pathlib import Path

import pytest
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.factory import SimFactory
from lunaris_live.sims.schema.teaching_spec import TeachingSpec
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType

ROOT = Path(__file__).resolve().parents[3]
MODEL = os.getenv("LUNARIS_MODEL_STRONG", "claude-opus-4-8")
CASES = json.loads((Path(__file__).parent / "fixtures/sim_domains.json").read_text())
pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio(loop_scope="module"),
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_domain_has_independently_verified_useful_simulator(case, tmp_path):
    node = ConceptNode.model_validate(case["node"])
    criterion = MasteryCriterion.model_validate(case["criterion"])
    verifier = ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    )
    factory = SimFactory(ClaudeSimModel(MODEL), verifier)
    scope = CostScope(
        run_id="p3-domain-" + case["id"],
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id="evaluation",
        price_book=PriceBook.current(),
    )
    with cost_scope(scope):
        result = await factory.build(node, criterion, run_id=scope.run_id)
    (tmp_path / "result.json").write_text(result.model_dump_json(by_alias=True, indent=2))
    if case["id"] == "unsuitable":
        assert result.status == "unsuitable"
        assert not result.candidates
        return
    assert result.status == "approved", result.reason
    independent = TeachingSpec(
        contract=result.bundle.spec.contract,
        source="Fixed independent Phase 3 domain oracle",
        source_version="2026-09-12-v1",
        cases=case["cases"],
    )
    checked = await verifier.verify(result.bundle.candidate, independent)
    (tmp_path / "independent.json").write_text(checked.model_dump_json(by_alias=True, indent=2))
    for index, shot in enumerate(checked.screenshots):
        (tmp_path / f"state-{index}.png").write_bytes(base64.b64decode(shot))
    assert checked.approved, checked.reasons
    assert all(call.cost_usd is not None for call in result.calls)
