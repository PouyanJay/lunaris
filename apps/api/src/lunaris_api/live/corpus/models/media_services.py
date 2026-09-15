from dataclasses import dataclass

from lunaris_live.corpus.video.protocols.inventory import IVideoInventory
from lunaris_live.graph import IGraphStore
from lunaris_live.session import ISessionStore
from lunaris_runtime.persistence import IVideoStorage

from ..protocols.access_guard import ICorpusAccessGuard


@dataclass(frozen=True)
class CorpusMediaServices:
    sessions: ISessionStore
    graphs: IGraphStore
    source_access: ICorpusAccessGuard
    inventory: IVideoInventory
    storage: IVideoStorage
