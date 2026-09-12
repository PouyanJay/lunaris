"""Cancellation during the blocking database admission cannot strand a granted lease."""

import asyncio
import threading
from unittest.mock import Mock

import pytest
from lunaris_api.live.session.coordination.coordinator import SessionCoordinator
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore
from lunaris_live.session.transactions.local_backend import LocalGraphTransactions


async def test_cancelled_acquire_releases_a_claim_that_arrives_late() -> None:
    sessions = MemorySessionStore()
    backend = LocalGraphTransactions(sessions, MemoryKnowledgeStore())
    entered, complete, released = threading.Event(), threading.Event(), threading.Event()
    wrapped = Mock(wraps=backend)

    def acquire(graph_id, *, owner_id):
        entered.set()
        assert complete.wait(2)
        return backend.acquire(graph_id, owner_id=owner_id)

    def release(claim):
        backend.release(claim)
        released.set()

    wrapped.acquire.side_effect, wrapped.release.side_effect = acquire, release
    coordinator = SessionCoordinator(sessions, wrapped)

    async def admitted_work():
        async with coordinator.graph("g", "owner"):
            pytest.fail("cancelled caller must not start work")

    caller = asyncio.create_task(admitted_work())
    assert await asyncio.to_thread(entered.wait, 2)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    complete.set()
    assert await asyncio.to_thread(released.wait, 2), "late granted claim was stranded"
    replacement = backend.acquire("g", owner_id="owner")
    assert replacement is not None
    backend.release(replacement)
