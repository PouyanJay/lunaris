import asyncio
from typing import Protocol
from uuid import uuid4

import structlog
from structlog.contextvars import bound_contextvars


class _Cleanup(Protocol):
    async def run_once(self) -> int: ...


async def run_voice_cleanup(cleanup: _Cleanup, *, interval_s: float = 60) -> None:
    """Sweep even while voice admission is disabled, so kill switches do not stop retention."""
    logger = structlog.get_logger()
    while True:
        with bound_contextvars(run_id=uuid4().hex):
            try:
                async with asyncio.timeout(120):
                    count = await cleanup.run_once()
                logger.info("live.voice.retention_swept", deleted_count=count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("live.voice.retention_deferred")
        await asyncio.sleep(interval_s)
