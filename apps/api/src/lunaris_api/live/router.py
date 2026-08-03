from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.graph import ConceptGraph, GraphCompilationError

from ..dependencies import OptionalUserIdDep
from .dependencies import LiveGraphServiceDep
from .schemas import LiveGraphRequest

router = APIRouter(prefix="/api/live/graphs", tags=["live"])


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
