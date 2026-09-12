import asyncio
from datetime import UTC, datetime

import structlog
from lunaris_runtime.credentials import credentials_for
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.metering import drain_cost_scope, enter_cost_scope, make_cost_scope
from lunaris_runtime.metering.cost_scope import CostScope
from lunaris_runtime.schema import CostSubjectType

from ...session import SessionStatus
from ..registry.cache_key import sim_cache_key
from ..registry.models.build_claim import SimBuildClaim
from ..schema.build_result import SimBuildResult
from .models.services import SimWorkerServices
from .models.worker_context import SimWorkerContext
from .schema.job import SimJob

_DRAIN_TIMEOUT_S = 5
_JOB_TIMEOUT_S = 240


class SimWorker:
    """Trusted supervisor only: claimed private jobs call the bounded factory exactly once."""

    def __init__(self, services: SimWorkerServices, *, context: SimWorkerContext) -> None:
        self._queue, self._assets, self._factory = services.queue, services.assets, services.factory
        self._context = context

    async def run_once(self) -> bool:
        try:
            async with asyncio.timeout(_JOB_TIMEOUT_S):
                job = await asyncio.to_thread(self._queue.take)
                if job is None:
                    return False
                bind_run_id(job.request.run_id, session_id=job.session_id)
                await self._process(job)
        except Exception:
            # The claim expires as indeterminate. Never retry potentially paid work automatically.
            structlog.get_logger().warning("live.sim.worker_unsettled")
        return True

    async def _eligible(self, job: SimJob) -> bool:
        if sim_cache_key(job.request.node, job.request.criterion) != job.cache_key:
            return False
        try:
            session = await asyncio.to_thread(
                self._context.sessions.load, job.session_id, owner_id=str(job.owner_id)
            )
        except FileNotFoundError:
            return False
        age = (datetime.now(UTC) - session.started_at).total_seconds()
        return session.status not in (SessionStatus.CLOSED, SessionStatus.ABANDONED) and (
            age < self._context.session_budget_s
        )

    async def _budget_available(self, job: SimJob) -> bool:
        context = self._context
        if context.subject_costs is None or context.session_budget_usd <= 0:
            return True
        async with asyncio.timeout(5):
            cost = await context.subject_costs.get(
                subject_type=CostSubjectType.LIVE_SESSION,
                subject_id=job.session_id,
                owner_id=str(job.owner_id),
            )
        return cost is None or cost.total_amount < context.session_budget_usd

    async def _process(self, job: SimJob) -> None:
        if not await self._eligible(job) or not await self._budget_available(job):
            await self._finish(
                job,
                SimBuildResult(
                    status="rejected", elapsed_ms=0, reason="Session unavailable or over budget."
                ),
            )
            return
        cost = self._cost(job)
        try:
            with enter_cost_scope(cost):
                result = await self._build(job)
            if not await self._eligible(job):
                result = result.model_copy(
                    update={
                        "status": "rejected",
                        "bundle": None,
                        "reason": "Session ended during generation.",
                    }
                )
            await self._finish(job, result)
        finally:
            await self._drain(cost)

    def _cost(self, job: SimJob) -> CostScope | None:
        return make_cost_scope(
            self._context.cost_events,
            self._context.subject_costs,
            run_id=job.request.run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=job.session_id,
            owner_id=str(job.owner_id),
        )

    async def _build(self, job: SimJob) -> SimBuildResult:
        with await credentials_for(self._context.credential_resolver, str(job.owner_id)):
            return await self._factory.build(
                job.request.node, job.request.criterion, run_id=job.request.run_id
            )

    async def _finish(self, job: SimJob, result: SimBuildResult) -> None:
        claim = SimBuildClaim(job.token, job.cache_key, job.owner_id, None)
        await asyncio.to_thread(self._assets.finish, claim, result)

    async def _drain(self, cost: CostScope | None) -> None:
        if cost is None:
            return
        try:
            async with asyncio.timeout(_DRAIN_TIMEOUT_S):
                await drain_cost_scope(cost, self._context.cost_events, self._context.subject_costs)
        except Exception:
            structlog.get_logger().warning("live.sim.cost_drain_failed")
