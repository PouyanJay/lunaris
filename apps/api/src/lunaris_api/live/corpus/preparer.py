import structlog
from lunaris_live.corpus.mapping.models.request import MappingRequest
from lunaris_live.corpus.mapping.protocols.mapper import IAssetMapper
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.corpus.video.protocols.inventory import IVideoInventory
from lunaris_live.graph import ConceptGraph

from .invalid import CorpusInvalidError
from .mapping_is_ready import mapping_is_ready

logger = structlog.get_logger()


class CorpusGraphPreparer:
    """Resolve approved mappings before the caller publishes one complete graph version."""

    def __init__(self, mapper: IAssetMapper, inventory: IVideoInventory) -> None:
        self._mapper = mapper
        self._inventory = inventory

    async def prepare(
        self, graph: ConceptGraph, *, snapshot: CorpusSnapshot, owner_id: str
    ) -> ConceptGraph:
        report = graph.grounding_report
        if (
            report is None
            or report.status != "passed"
            or report.source_digest != snapshot.source.digest
        ):
            return graph.model_copy(
                update={"corpus": snapshot.source.model_copy(update={"status": "failed"})}
            )
        inventory = await self._inventory.load(
            snapshot.source.course_id, owner_id=owner_id, run_id=snapshot.source.run_id
        )
        mapped = await self._mapper.map(
            MappingRequest(
                graph=graph,
                snapshot=snapshot,
                inventory=inventory,
                run_id=snapshot.source.run_id,
            )
        )
        if mapped.graph_id != graph.graph_id:
            raise CorpusInvalidError()
        status = "verified" if mapping_is_ready(mapped, snapshot) else "failed"
        logger.info(
            "live.corpus.prepared",
            run_id=snapshot.source.run_id,
            graph_id=graph.graph_id,
            status=status,
        )
        return mapped.model_copy(
            update={"corpus": snapshot.source.model_copy(update={"status": status})}
        )
