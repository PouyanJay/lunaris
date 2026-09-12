"""Lease renewal must stop an admitted caller before its fence can expire."""

import asyncio
from unittest.mock import Mock

import pytest
from lunaris_api.live.session.coordination import lease as lease_module
from lunaris_api.live.session.coordination.lease import GraphLease
from lunaris_live.session.transactions.models.claim import GraphClaim


@pytest.mark.parametrize("failure", [False, RuntimeError("database unavailable")])
async def test_lost_renewal_cancels_work_and_releases_the_claim(monkeypatch, failure) -> None:
    monkeypatch.setattr(lease_module, "_RENEW_INTERVAL_S", 0.001)
    backend = Mock()
    backend.renew.side_effect = [True, failure] if isinstance(failure, Exception) else None
    if failure is False:
        backend.renew.side_effect = [True, False]
    claim = GraphClaim("graph", "owner", "token")
    leases: list[GraphLease] = []

    async def admitted_work() -> None:
        held = GraphLease(claim, backend)
        leases.append(held)
        try:
            await asyncio.Event().wait()
        finally:
            await held.close()

    work = asyncio.create_task(admitted_work())
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(work, timeout=2)
    assert backend.renew.call_count == 2
    assert leases[0].lost and leases[0].closed
    backend.release.assert_called_once_with(claim)
    await leases[0].close()
    backend.release.assert_called_once_with(claim)
