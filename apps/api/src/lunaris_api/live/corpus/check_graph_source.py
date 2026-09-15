from uuid import uuid4

from lunaris_live.graph import ConceptGraph
from structlog.contextvars import get_contextvars

from .models.access_policy import CorpusAccessPolicy
from .protocols.access_guard import ICorpusAccessGuard
from .unavailable import CorpusUnavailableError


def _run_id() -> str:
    context = get_contextvars()
    return str(context.get("run_id") or context.get("request_id") or uuid4().hex)


async def check_graph_source(
    graph: ConceptGraph,
    access: ICorpusAccessGuard | None,
    owner_id: str | None,
    *,
    policy: CorpusAccessPolicy = CorpusAccessPolicy.TEACH,
) -> None:
    if graph.corpus is None:
        return
    if access is None:
        raise CorpusUnavailableError
    await access.check(graph, owner_id=owner_id, run_id=_run_id(), policy=policy)
