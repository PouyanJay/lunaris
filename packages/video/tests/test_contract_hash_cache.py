"""ContractHashCache tests: a content-addressed video cache — same contract hash hits, a different
one misses, and the bound evicts the oldest entry."""

from lunaris_video.models import RenderedVideo
from lunaris_video.pipeline import ContractHashCache


def _video(tag: bytes) -> RenderedVideo:
    return RenderedVideo(mp4=tag, poster=tag, contracts_json=tag, timing_json=tag)


async def test_store_then_fetch_returns_the_same_video() -> None:
    # Arrange
    cache = ContractHashCache()
    video = _video(b"v1")
    await cache.store("hash-a", video)

    # Act / Assert
    assert await cache.fetch("hash-a") is video


async def test_unknown_hash_misses() -> None:
    # Arrange
    cache = ContractHashCache()

    # Act / Assert
    assert await cache.fetch("never-stored") is None


async def test_capacity_evicts_the_least_recently_used() -> None:
    # Arrange — capacity 2; store a, b, then touch a so b is the LRU.
    cache = ContractHashCache(capacity=2)
    await cache.store("a", _video(b"a"))
    await cache.store("b", _video(b"b"))
    await cache.fetch("a")  # a becomes most-recently used

    # Act — c overflows; b (the LRU) is evicted, a survives.
    await cache.store("c", _video(b"c"))

    # Assert
    assert await cache.fetch("b") is None
    assert await cache.fetch("a") is not None
    assert await cache.fetch("c") is not None
