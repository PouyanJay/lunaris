from collections import OrderedDict

import structlog

from lunaris_video.models import RenderedVideo

_logger = structlog.get_logger(__name__)

_DEFAULT_CAPACITY = 32


class ContractHashCache:
    """An in-process LRU cache of finished videos, keyed by contract hash.

    Skips re-rendering when a contract recurs within a worker's lifetime (a retry, or two lessons
    that planned to the identical contract). It is deliberately in-memory for V1: the contract +
    artifacts are also persisted to storage per job, so a durable cross-process cache (storage
    lookup by contract hash) is a later refinement, not a correctness gap — a cold worker simply
    re-renders. Bounded so a long-lived worker cannot grow unboundedly.
    """

    def __init__(self, *, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._capacity = capacity
        self._entries: OrderedDict[str, RenderedVideo] = OrderedDict()

    async def fetch(self, contract_hash: str) -> RenderedVideo | None:
        video = self._entries.get(contract_hash)
        if video is not None:
            self._entries.move_to_end(contract_hash)
            _logger.info("contract_cache.hit", contract_hash=contract_hash)
        return video

    async def store(self, contract_hash: str, video: RenderedVideo) -> None:
        self._entries[contract_hash] = video
        self._entries.move_to_end(contract_hash)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
