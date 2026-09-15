from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...schemas.snapshot import CorpusSnapshot
from ...video.schemas.inventory import VideoInventory

if TYPE_CHECKING:
    from ....graph.schema import ConceptGraph


@dataclass(frozen=True)
class MappingRequest:
    graph: ConceptGraph
    snapshot: CorpusSnapshot
    inventory: VideoInventory
    run_id: str
