"""Paid tutor reactions use the same independently checked published teaching bundles."""

import json
import os
from pathlib import Path
from time import monotonic
from unittest.mock import Mock
from uuid import uuid4

import pytest
from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.grounded_coach import GroundedSimCoach
from lunaris_live.sims.registry.schema.asset import SimAsset
from lunaris_live.sims.schema.event import SimEvent
from lunaris_live.sims.schema.teaching_spec import TeachingSpec
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType

ROOT = Path(__file__).resolve().parents[3]
MODEL = os.getenv("LUNARIS_MODEL_STRONG", "claude-opus-4-8")
EVIDENCE = ROOT / "documentation/evaluations/live-sim-domains-2026-09-12"
CASES = json.loads((Path(__file__).parent / "fixtures/sim_domains.json").read_text())[:3]
pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio(loop_scope="module"),
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


def _expected(domain, state):
    if domain == "algorithms":
        return {"comparisons": str(int(state["n"] * (state["n"] - 1) / 2))}
    if domain == "physics":
        return {"current": f"{state['voltage'] / state['resistance']:.2f}"}
    return {"profit": str(int((state["price"] - 10) * state["quantity"] - 100))}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_real_tutor_reaction_commands_obey_independent_domain_relationship(case, tmp_path):
    raw = json.loads((EVIDENCE / f"approved-{case['id']}.json").read_text())
    owner = str(uuid4())
    asset = SimAsset(
        id=uuid4(), owner_id=owner, cache_key="a" * 64, bundle=raw["bundle"], calls=raw["calls"]
    )
    store = Mock()
    store.load.return_value = asset
    coach = GroundedSimCoach(ClaudeSimModel(MODEL), store, owner_id=owner)
    event = SimEvent(
        version=1,
        instance_id="eval-turn",
        turn_seq=1,
        sequence=1,
        app_id=str(asset.id),
        kind="param_changed",
        state=case["cases"][1]["state"],
    )
    scope = CostScope(
        run_id="p3-coach-" + case["id"],
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id="evaluation",
        price_book=PriceBook.current(),
    )
    started = monotonic()
    with cost_scope(scope):
        reaction = await coach.respond(asset.bundle.spec.contract, event, run_id=scope.run_id)
    artifact = {
        "domain": case["id"],
        "gesture": event.state,
        "reaction": reaction.model_dump(),
        "model": MODEL,
        "costUsd": sum(entry.amount for entry in scope.entries),
        "elapsedMs": int((monotonic() - started) * 1000),
    }
    (tmp_path / "reaction.json").write_text(json.dumps(artifact, indent=2))
    cases = [
        {"state": reaction.state, "outputs": _expected(case["id"], reaction.state)},
        *[example for example in case["cases"] if example["state"] != reaction.state],
    ]
    independent = TeachingSpec(
        contract=asset.bundle.spec.contract,
        source="fixed domain oracle",
        source_version="2026-09-12-v1",
        cases=cases,
    )
    checked = await ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    ).verify(asset.bundle.candidate, independent)
    assert checked.approved, checked.reasons
    assert reaction.text.strip()
    store.load.assert_called_once_with(str(asset.id), owner_id=owner)
