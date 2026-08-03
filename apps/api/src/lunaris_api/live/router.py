from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.graph import (
    ConceptGraph,
    GraphCompilationError,
    GraphVersionConflictError,
)
from lunaris_runtime.persistence import PersistenceError

from ..dependencies import OptionalUserIdDep
from .dependencies import LiveGraphServiceDep
from .schemas import LiveGraphExtendRequest, LiveGraphRequest

logger = structlog.get_logger()

router = APIRouter(prefix="/api/live/graphs", tags=["live"])

_UNAVAILABLE = "Live is having trouble reaching its storage. Try again shortly."


@router.post("", response_model=ConceptGraph, status_code=status.HTTP_201_CREATED)
async def compile_graph(
    payload: LiveGraphRequest,
    service: LiveGraphServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> ConceptGraph:
    """Compile a topic into a concept graph and persist it.

    The generated ``run_id`` comes back in ``X-Run-Id`` so one compile can be triangulated across
    every layer's logs — the same correlation contract Studio's build endpoints hold.
    """
    run_id = uuid4().hex
    response.headers["X-Run-Id"] = run_id
    try:
        return await service.compile(payload.topic, run_id=run_id, owner_id=owner_id)
    except PersistenceError as exc:
        # The store itself failed. Logged with the traceback because nothing below the router does
        # — guard translates the driver's error and the stores stay silent — so without this a real
        # outage is a bare 500 with no way to tell what broke.
        logger.warning("live.graph.persistence_failed", run_id=run_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
            headers={"X-Run-Id": run_id},
        ) from exc
    except TimeoutError as exc:
        # The compile overran its budget and was abandoned. Distinct from the 502 below because the
        # remedy differs: nothing was wrong with the topic, so retrying it verbatim is reasonable.
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Mapping this topic took too long. Try again.",
            headers={"X-Run-Id": run_id},
        ) from exc
    except GraphCompilationError as exc:
        # The model gave us nothing usable. Say so — an empty graph would read to the learner as
        # "your topic has no concepts in it" rather than "we failed", and they'd have no reason to
        # retry. 502: the failure is upstream of us, and retrying is a reasonable next step.
        # The run id has to ride the error too: raising an HTTPException discards the response
        # object built above, and a failed compile is precisely when someone needs to go and read
        # the logs for it.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't map this topic. Try again, or rephrase it.",
            headers={"X-Run-Id": run_id},
        ) from exc


@router.get("/{graph_id}", response_model=ConceptGraph)
async def get_graph(
    graph_id: str,
    service: LiveGraphServiceDep,
    owner_id: OptionalUserIdDep,
) -> ConceptGraph:
    """Re-read a compiled graph. Another owner's graph is 404, not 403 — a graph's existence is
    itself owner-scoped information."""
    try:
        return await service.load(graph_id, owner_id=owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found"
        ) from exc


@router.post("/{graph_id}/extend", response_model=ConceptGraph)
async def extend_graph(
    graph_id: str,
    payload: LiveGraphExtendRequest,
    service: LiveGraphServiceDep,
    response: Response,
    owner_id: OptionalUserIdDep,
) -> ConceptGraph:
    """Grow a compiled map onto one branch, for a request it does not currently cover (C1).

    This is the endpoint that keeps a session from having to choose between refusing a question and
    railroading past it. It is a plain request rather than a job: a cold compile takes minutes, but
    an extension has to come back inside a pause a tutor can talk over.
    """
    run_id = uuid4().hex
    response.headers["X-Run-Id"] = run_id
    try:
        return await service.extend(
            graph_id,
            request=payload.request,
            anchors=payload.anchors,
            run_id=run_id,
            owner_id=owner_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found"
        ) from exc
    except GraphVersionConflictError as exc:
        # Caught ahead of PersistenceError below, which it subclasses — a lost race is a specific,
        # actionable outcome and must not be flattened into "the database broke".
        # The map moved while this was being built. 409 so the caller re-reads and decides again
        # with the newer map — a judgement the session owns, not something to retry blindly here.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This map changed while the answer was being prepared. Try again.",
            headers={"X-Run-Id": run_id},
        ) from exc
    except PersistenceError as exc:
        # The store itself failed. Logged with the traceback because nothing below the router does
        # — guard translates the driver's error and the stores stay silent — so without this a real
        # outage is a bare 500 with no way to tell what broke.
        logger.warning("live.graph.persistence_failed", run_id=run_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
            headers={"X-Run-Id": run_id},
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="That took too long to work out. Try again.",
            headers={"X-Run-Id": run_id},
        ) from exc
    except GraphCompilationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't work out what to add for that. Try rephrasing it.",
            headers={"X-Run-Id": run_id},
        ) from exc
