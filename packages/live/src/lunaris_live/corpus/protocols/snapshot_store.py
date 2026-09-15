from typing import Protocol

from ..models.snapshot_key import SnapshotKey
from ..schemas.snapshot import CorpusSnapshot


class ICorpusSnapshotStore(Protocol):
    def save(self, snapshot: CorpusSnapshot, *, owner_id: str) -> CorpusSnapshot:
        """Insert immutably; return the existing snapshot for an identical source revision."""
        ...

    def load(self, key: SnapshotKey) -> CorpusSnapshot: ...
