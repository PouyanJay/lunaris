from typing import Protocol

from lunaris_video.models import RenderedVideo


class IRenderCache(Protocol):
    """Content-addressed cache of finished videos, keyed by contract hash (plan principle 5).

    The contract is regeneration-stable by design, so an unchanged contract with cached artifacts
    can skip Stage 2+ (code → render → QA → assemble) entirely. ``fetch`` returns ``None`` on a
    miss; ``store`` records a freshly assembled video under its contract hash.
    """

    async def fetch(self, contract_hash: str) -> RenderedVideo | None: ...

    async def store(self, contract_hash: str, video: RenderedVideo) -> None: ...
