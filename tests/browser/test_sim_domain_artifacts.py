"""Replay selected real model artifacts against fixed, independent numeric oracles."""

import json
from pathlib import Path

import pytest
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.schema.build_result import SimBuildResult
from lunaris_live.sims.schema.teaching_spec import TeachingSpec

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "packages/live/tests/fixtures/sim_domains.json").read_text())[:3]
pytestmark = pytest.mark.browser


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_approved_domain_artifact_matches_fixed_numeric_oracle(case):
    evidence = ROOT / "documentation/evaluations/live-sim-domains-2026-09-12"
    result = SimBuildResult.model_validate_json(
        (evidence / f"approved-{case['id']}.json").read_text()
    )
    spec = TeachingSpec(
        contract=result.bundle.spec.contract,
        source="fixed independent domain oracle",
        source_version="2026-09-12-v1",
        cases=case["cases"],
    )
    checked = await ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    ).verify(result.bundle.candidate, spec)
    assert checked.approved, checked.reasons
