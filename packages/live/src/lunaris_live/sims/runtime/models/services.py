from dataclasses import dataclass

from ...protocols.factory import ISimFactory
from ...registry.protocols.asset_store import ISimAssetStore
from ..protocols.queue import ISimQueue


@dataclass(frozen=True)
class SimWorkerServices:
    queue: ISimQueue
    assets: ISimAssetStore
    factory: ISimFactory
