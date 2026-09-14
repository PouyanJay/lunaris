from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import structlog
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.models.transcription import Transcription
from lunaris_live.voice.protocols.provider import IVoiceProvider
from lunaris_runtime.credentials import credentials_for
from lunaris_runtime.metering import CostScope, drain_cost_scope, enter_cost_scope, make_cost_scope
from lunaris_runtime.schema import CostSubjectType

from ..session.spent_past_ceiling import spent_past_ceiling
from .metering_context import VoiceMeteringContext
from .metering_dependencies import VoiceMeteringDependencies

_logger = structlog.get_logger(__name__)
_CLEANUP_TIMEOUT_S = 3.0


class MeteredVoiceProvider:
    """Attribute actual provider work to its session, including interrupted streams.

    The observed session ceiling is shared with text turns; atomic voice reservations belong
    to the durable voice service. Cached operations never enter this adapter.
    """

    def __init__(
        self,
        provider: IVoiceProvider,
        context: VoiceMeteringContext,
        dependencies: VoiceMeteringDependencies,
    ) -> None:
        self._provider = provider
        self._context = context
        self._dependencies = dependencies

    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription:
        async with self._scope(run_id):
            return await self._provider.transcribe(audio, run_id=run_id)

    async def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        async with self._scope(run_id):
            stream = self._provider.speak(text, run_id=run_id)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                # AsyncIterator does not require aclose, but provider generators do expose it.
                # Close while credentials and metering remain bound: providers meter in finally.
                close = getattr(stream, "aclose", None)
                if close is not None:
                    with anyio.move_on_after(_CLEANUP_TIMEOUT_S, shield=True) as cleanup:
                        await close()
                    if cleanup.cancel_called:
                        self._log_timeout("upstream", run_id)

    @asynccontextmanager
    async def _scope(self, run_id: str) -> AsyncIterator[None]:
        context, dependencies = self._context, self._dependencies
        spent = await spent_past_ceiling(
            dependencies.subject_cost_store,
            session_id=context.session_id,
            owner_id=context.owner_id,
            ceiling_usd=context.session_cost_ceiling_usd,
        )
        if spent is not None:
            raise VoiceError("This session has reached its spending limit.", status_code=429)
        cost = make_cost_scope(
            dependencies.cost_event_store,
            dependencies.subject_cost_store,
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=context.session_id,
            owner_id=context.owner_id,
        )
        credentials = await credentials_for(dependencies.credential_resolver, context.owner_id)
        with credentials, enter_cost_scope(cost):
            try:
                yield
            finally:
                await self._drain(cost, run_id)

    async def _drain(self, cost: CostScope | None, run_id: str) -> None:
        # Starlette cancels streaming bodies through an AnyIO cancel scope. Shielding
        # ensures that a disconnect does not discard accepted provider usage.
        with anyio.move_on_after(_CLEANUP_TIMEOUT_S, shield=True) as cleanup:
            await drain_cost_scope(
                cost, self._dependencies.cost_event_store, self._dependencies.subject_cost_store
            )
        if cleanup.cancel_called:
            self._log_timeout("cost_drain", run_id)

    def _log_timeout(self, operation: str, run_id: str) -> None:
        _logger.warning(
            "live.voice.cleanup_timed_out",
            operation=operation,
            run_id=run_id,
            session_id=self._context.session_id,
        )
