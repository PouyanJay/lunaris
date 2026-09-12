import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TypeVar

import structlog
from lunaris_live.session import ISessionStore, Session
from lunaris_live.session.transactions.models.claim import GraphClaim
from lunaris_live.session.transactions.models.mutation import SessionMutation
from lunaris_live.session.transactions.protocols.backend import IGraphTransactionBackend
from lunaris_runtime.persistence import PersistenceError

from .busy import LiveGraphBusyError
from .indeterminate import IndeterminateLiveTurnError
from .lease import GraphLease

_current: ContextVar[GraphLease | None] = ContextVar("live_graph_lease", default=None)
_T = TypeVar("_T")


class SessionCoordinator:
    def __init__(self, sessions: ISessionStore, backend: IGraphTransactionBackend) -> None:
        self._sessions, self._backend = sessions, backend
        self._cleanups: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def graph(
        self, graph_id: str, owner_id: str | None, *, wait_s: float = 0
    ) -> AsyncIterator[GraphLease]:
        existing = _current.get()
        if (
            existing
            and existing.owner_task is asyncio.current_task()
            and (existing.claim.graph_id, existing.claim.owner_id) == (graph_id, owner_id)
        ):
            yield existing
            return
        claim = await self._claim(graph_id, owner_id, wait_s)
        if claim is None:
            raise LiveGraphBusyError()
        lease = GraphLease(claim, self._backend)
        binding = _current.set(lease)
        try:
            yield lease
        finally:
            _current.reset(binding)
            if not lease.detached:
                await lease.close()

    async def _claim(self, graph_id: str, owner_id: str | None, wait_s: float) -> GraphClaim | None:
        deadline = asyncio.get_running_loop().time() + wait_s
        delay = 0.02
        while True:
            acquiring = asyncio.create_task(
                asyncio.to_thread(self._backend.acquire, graph_id, owner_id=owner_id)
            )
            try:
                claim = await asyncio.shield(acquiring)
            except asyncio.CancelledError:
                cleanup = asyncio.create_task(self._release_late_claim(acquiring))
                self._cleanups.add(cleanup)
                cleanup.add_done_callback(self._cleanups.discard)
                raise
            remaining = deadline - asyncio.get_running_loop().time()
            if claim is not None or remaining <= 0:
                return claim
            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * 2, 0.25)

    async def _release_late_claim(self, acquiring: asyncio.Task[GraphClaim | None]) -> None:
        try:
            claim = await acquiring
            if claim is not None:
                async with asyncio.timeout(10):
                    await asyncio.to_thread(self._backend.release, claim)
        except Exception:
            structlog.get_logger().warning("live.graph.late_claim_release_failed")

    @asynccontextmanager
    async def session(self, session_id: str, owner_id: str | None) -> AsyncIterator[GraphLease]:
        # Identity only before admission. The service re-reads mutable state under this lease.
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        async with self.graph(session.graph_id, owner_id) as lease:
            yield lease

    def _active(self) -> GraphLease:
        lease = _current.get()
        if lease is None or lease.closed or lease.lost:
            raise PersistenceError("No active graph transaction")
        return lease

    async def paid(self, snapshot: Session | str, operation: str) -> None:
        lease = self._active()
        state = (
            json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
            if isinstance(snapshot, Session)
            else snapshot
        )
        key = hashlib.sha256((operation + "\n" + state).encode()).hexdigest()
        if not await asyncio.to_thread(lease.backend.paid, lease.claim, key):
            raise IndeterminateLiveTurnError()

    async def commit(self, mutation: SessionMutation) -> None:
        lease = self._active()
        await asyncio.to_thread(lease.backend.commit, lease.claim, mutation)

    async def run_detached(
        self, lease: GraphLease, work: Callable[[], Coroutine[object, object, _T]]
    ) -> _T:
        try:
            return await work()
        finally:
            await lease.close()
