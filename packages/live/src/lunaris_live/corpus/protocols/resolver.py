from typing import Protocol

from ..schemas.reference import CorpusReference
from ..schemas.snapshot import CorpusSnapshot


class ICorpusResolver(Protocol):
    async def resolve(
        self, reference: CorpusReference, *, owner_id: str, run_id: str
    ) -> CorpusSnapshot:
        """Read an owner-authorized snapshot or raise FileNotFoundError before inference."""
        ...
