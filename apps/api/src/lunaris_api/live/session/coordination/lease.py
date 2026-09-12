import asyncio
from contextlib import suppress

import structlog
from lunaris_live.session.transactions.models.claim import GraphClaim
from lunaris_live.session.transactions.protocols.backend import IGraphTransactionBackend
from lunaris_runtime.persistence import PersistenceError

_RENEW_INTERVAL_S = 15


class GraphLease:
    """A fenced lease survives a detached stream and stops paid work if renewal fails."""

    def __init__(self, claim: GraphClaim, backend: IGraphTransactionBackend) -> None:
        self.claim, self.backend = claim, backend
        self.owner_task = asyncio.current_task()
        self.detached = False
        self.closed = False
        self.lost = False
        self._heartbeat = asyncio.create_task(self._renew())

    async def _renew(self) -> None:
        try:
            while True:
                await asyncio.sleep(_RENEW_INTERVAL_S)
                async with asyncio.timeout(10):
                    renewed = await asyncio.to_thread(self.backend.renew, self.claim)
                if not renewed:
                    raise PersistenceError("Graph lease lost")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.lost = True
            structlog.get_logger().warning("live.graph.lease_lost", graph_id=self.claim.graph_id)
            if self.owner_task is not None:
                self.owner_task.cancel()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await self._heartbeat
        try:
            async with asyncio.timeout(10):
                await asyncio.to_thread(self.backend.release, self.claim)
        except Exception:
            structlog.get_logger().warning(
                "live.graph.release_failed", graph_id=self.claim.graph_id
            )
