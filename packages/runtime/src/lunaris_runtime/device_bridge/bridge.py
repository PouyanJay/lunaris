"""The per-run device bridge: the completion queue between a build and the learner's browser.

A device-compute Draft build keeps its orchestration on the server but serves every LLM completion
from the learner's tab: the run's chat model parks each completion request here
(:meth:`DeviceBridge.complete`), the tab long-polls them over HTTP (:meth:`DeviceBridge.claim`) and
posts each result back (:meth:`DeviceBridge.resolve`), which resolves the awaiting future. One
bridge per run, in-memory — builds already run as in-process background tasks, so the bridge shares
their lifetime.

The failure contract matters as much as the happy path: a tab that stops polling (closed / laptop
asleep) or never answers a claimed completion must FAIL the build promptly via
:class:`DeviceBridgeDisconnectedError` — a hung run is the one unacceptable outcome.

Sibling-pair module (the documented one-export exception, like ``credentials/run_credentials``):
``BridgeCompletionRequest`` is produced and consumed only by ``DeviceBridge`` — the pair is one
contract and is exported together.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4

import structlog

from .errors import DeviceBridgeDisconnectedError
from .limits import BridgeLimits

logger = structlog.get_logger()

# How often a parked completion re-checks the tab's liveness. Bounded below so a tiny (test)
# liveness window still ticks, and above so the default 75s window isn't polled needlessly.
_WATCHDOG_FLOOR_S = 0.01
_WATCHDOG_CEILING_S = 1.0


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

    def __init__(self, *, run_id: str, limits: BridgeLimits | None = None) -> None:
        self._run_id = run_id
        self._limits = limits or BridgeLimits()
        self._queue: asyncio.Queue[BridgeCompletionRequest] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[str]] = {}
        # The tab's last sign of life. Starts at creation: a tab that NEVER polls must trip the
        # liveness bound too, measured from when the build admitted the bridge.
        self._last_seen = time.monotonic()

    @property
    def run_id(self) -> str:
        return self._run_id

    async def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Park one completion for the tab and await its posted result (the model side).

        Raises :class:`DeviceBridgeDisconnectedError` instead of hanging when the tab goes
        silent past ``liveness_s``, or stays alive but never answers within
        ``completion_timeout_s`` (a wedged on-device engine).
        """
        request = BridgeCompletionRequest(request_id=uuid4().hex, messages=tuple(messages))
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request.request_id] = future
        self._queue.put_nowait(request)
        logger.info(
            "device_bridge_completion_queued", run_id=self._run_id, request_id=request.request_id
        )
        deadline = time.monotonic() + self._limits.completion_timeout_s
        # Tick at a quarter of the TIGHTER bound so whichever fires first is checked at least
        # four times per window — a coarse tick would overshoot a tight completion deadline.
        tightest = min(self._limits.liveness_s, self._limits.completion_timeout_s)
        tick = min(_WATCHDOG_CEILING_S, max(_WATCHDOG_FLOOR_S, tightest / 4))
        try:
            while True:
                try:
                    # shield: a watchdog tick must not cancel the future other ticks re-await.
                    return await asyncio.wait_for(asyncio.shield(future), timeout=tick)
                except TimeoutError:
                    self._check_liveness(deadline, request.request_id)
        finally:
            self._pending.pop(request.request_id, None)

    def _check_liveness(self, deadline: float, request_id: str) -> None:
        """One watchdog tick: fail the wait when the tab is silent or the answer is overdue."""
        now = time.monotonic()
        silence = now - self._last_seen
        if silence >= self._limits.liveness_s:
            logger.warning(
                "device_bridge_disconnected",
                run_id=self._run_id,
                request_id=request_id,
                silence_s=round(silence, 1),
            )
            raise DeviceBridgeDisconnectedError(
                "The device serving this build stopped responding — its tab must stay open "
                "until the build finishes."
            )
        if now >= deadline:
            logger.warning(
                "device_bridge_completion_timed_out", run_id=self._run_id, request_id=request_id
            )
            raise DeviceBridgeDisconnectedError(
                "The device serving this build never answered a completion — its on-device "
                "model may have stalled."
            )

    async def claim(self, *, wait_s: float) -> list[BridgeCompletionRequest]:
        """Long-poll: wait up to ``wait_s`` for at least one queued request, then drain the rest.

        An empty list means nothing was queued within the window — the tab simply polls again.
        Every call refreshes the tab's liveness, on entry and exit: a poll that parked for the
        full window is still a live tab.
        """
        self._last_seen = time.monotonic()
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=wait_s)
        except TimeoutError:
            self._last_seen = time.monotonic()
            return []
        claimed = [first]
        while not self._queue.empty():
            claimed.append(self._queue.get_nowait())
        self._last_seen = time.monotonic()
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

    def fail_pending(self, reason: str) -> None:
        """Fail every in-flight completion (run teardown): the model side unblocks with the
        disconnect error and late tab answers are rejected. Idempotent."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DeviceBridgeDisconnectedError(reason))
