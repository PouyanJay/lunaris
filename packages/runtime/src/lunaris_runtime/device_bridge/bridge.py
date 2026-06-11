"""The per-run device bridge: the completion queue between a build and the learner's browser.

A device-compute Draft build keeps its orchestration on the server but serves every LLM completion
from the learner's tab: the run's chat model parks each completion request here
(:meth:`DeviceBridge.complete`), the tab long-polls them over HTTP (:meth:`DeviceBridge.claim`) and
posts each result back (:meth:`DeviceBridge.resolve`), which resolves the awaiting future. One
bridge per run, in-memory — builds already run as in-process background tasks, so the bridge shares
their lifetime.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class BridgeCompletionRequest:
    """One pending completion: the messages the tab must run on its on-device model."""

    request_id: str
    messages: tuple[Mapping[str, str], ...]


class DeviceBridge:
    """The completion queue for one device-compute run.

    The model side awaits :meth:`complete`; the HTTP side drains :meth:`claim` and settles
    :meth:`resolve`. All methods run on the API's event loop (the run task and the bridge router
    share it), so plain dict/queue state needs no locking.
    """

    def __init__(self, *, run_id: str) -> None:
        self._run_id = run_id
        self._queue: asyncio.Queue[BridgeCompletionRequest] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[str]] = {}

    @property
    def run_id(self) -> str:
        return self._run_id

    async def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Park one completion for the tab and await its posted result (the model side)."""
        request = BridgeCompletionRequest(request_id=uuid4().hex, messages=tuple(messages))
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request.request_id] = future
        self._queue.put_nowait(request)
        logger.info(
            "device_bridge_completion_queued", run_id=self._run_id, request_id=request.request_id
        )
        try:
            return await future
        finally:
            self._pending.pop(request.request_id, None)

    async def claim(self, *, wait_s: float) -> list[BridgeCompletionRequest]:
        """Long-poll: wait up to ``wait_s`` for at least one queued request, then drain the rest.

        An empty list means nothing was queued within the window — the tab simply polls again.
        """
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=wait_s)
        except TimeoutError:
            return []
        claimed = [first]
        while not self._queue.empty():
            claimed.append(self._queue.get_nowait())
        return claimed

    def resolve(self, request_id: str, text: str) -> bool:
        """Settle a pending completion with the tab's result. ``False`` when the request is
        unknown or already settled (the caller surfaces a conflict)."""
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(text)
        logger.info("device_bridge_completion_served", run_id=self._run_id, request_id=request_id)
        return True
