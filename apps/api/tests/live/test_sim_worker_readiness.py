"""Supervisor admission waits for actual behavior and isolation evidence."""

from unittest.mock import AsyncMock

import pytest
from lunaris_live.sims.schema.verification_report import VerificationReport


def _report(approved):
    return VerificationReport(
        content_hash="a" * 64,
        spec_hash="b" * 64,
        approved=approved,
        checks_passed=4 if approved else 0,
        elapsed_ms=1,
    )


@pytest.mark.parametrize("results", [[False], [True, True]])
async def test_worker_refuses_broken_or_permissive_verifier(results):
    from lunaris_api.live.verify_sim_worker import verify_worker_environment

    verifier = AsyncMock()
    verifier.verify.side_effect = [_report(approved) for approved in results]
    with pytest.raises(RuntimeError, match="Verifier startup"):
        await verify_worker_environment(verifier)


async def test_worker_requires_both_correct_behavior_and_network_rejection():
    from lunaris_api.live.verify_sim_worker import verify_worker_environment

    verifier = AsyncMock()
    verifier.verify.side_effect = [_report(True), _report(False)]
    await verify_worker_environment(verifier)
    safe, unsafe = verifier.verify.call_args_list
    assert safe.args[0].html != unsafe.args[0].html
    assert "fetch(" in unsafe.args[0].html
    assert [case.outputs for case in safe.args[1].cases] == [
        {"y": "y = 4"},
        {"y": "y = 8"},
        {"y": "y = 0"},
    ]
