from collections.abc import AsyncIterator
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from lunaris_live.graph import (
    CompileProgress,
    ConceptGraph,
    GraphCompilationError,
    GraphVersionConflictError,
)
from lunaris_runtime.persistence import PersistenceError

from ..dependencies import OptionalUserIdDep
from .dependencies import LiveGraphServiceDep
from .schemas import CompileFailure, LiveGraphExtendRequest, LiveGraphRequest

logger = structlog.get_logger()

router = APIRouter(prefix="/api/live/graphs", tags=["live"])

_UNAVAILABLE = "Live is having trouble reaching its storage. Try again shortly."
# The learner-facing copy for a failed cold compile, shared by both entry points: the same failure
# must read the same whether it arrives as a 502 body or as a frame on a stream.
_UNMAPPABLE = "Couldn't map this topic. Try again, or rephrase it."
_TOO_SLOW = "Mapping this topic took too long. Try again."


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
    except Exception as exc:
        if isinstance(exc, PersistenceError):
            # The store itself failed. Logged with the traceback because nothing below the router
            # does — guard translates the driver's error and the stores stay silent — so without
            # this a real outage is a bare 500 with no way to tell what broke.
            logger.warning("live.graph.persistence_failed", run_id=run_id, exc_info=True)
        http_status, detail = _failure_of(exc)
        if http_status == status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise
        # The run id has to ride the error: raising an HTTPException discards the response object
        # built above, and a failed compile is precisely when someone needs to read the logs for it.
        raise HTTPException(
            status_code=http_status, detail=detail, headers={"X-Run-Id": run_id}
        ) from exc


@router.get("/stream")
async def stream_graph(
    service: LiveGraphServiceDep,
    owner_id: OptionalUserIdDep,
    topic: str = Query(min_length=1, max_length=200),
) -> StreamingResponse:
    """Compile a topic, narrating the compile as Server-Sent Events.

    The same work as ``POST /api/live/graphs``, which survives as the durable await-full entry
    point — but a cold compile runs for minutes, and this is the only surface that can tell a
    learner what those minutes are being spent on. Emits ``progress`` per beat, then one terminal
    ``graph``. ``run_id`` and ``graph_id`` go out in headers *before* the body, so a stream that
    drops can re-attach by reading the graph rather than paying for the compile twice.
    """
    if not topic.strip():
        # ``min_length`` admits "   ", which would compile a map of nothing and bill for it. Refused
        # here while a real status code can still be sent — once the body opens, it cannot.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="topic must not be blank"
        )

    run_id = uuid4().hex
    graph_id = uuid4().hex

    async def frames() -> AsyncIterator[str]:
        try:
            async for kind, payload in service.stream(
                topic, graph_id=graph_id, run_id=run_id, owner_id=owner_id
            ):
                yield _frame(kind, payload)
        except Exception as exc:
            # A stream's status was sent before the work began, so a failure can only be said in the
            # body. Without this the connection just closes, and the web cannot tell a compile that
            # failed from one whose connection dropped — the first is worth retrying, the second is
            # worth re-attaching to.
            logger.warning(
                "live.graph.stream_failed", run_id=run_id, graph_id=graph_id, exc_info=True
            )
            yield _frame("error", CompileFailure(message=_failure_of(exc)[1], run_id=run_id))

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "X-Run-Id": run_id,
            "X-Graph-Id": graph_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering so frames flush live
        },
    )


def _frame(kind: str, payload: CompileProgress | ConceptGraph | CompileFailure) -> str:
    """One SSE frame — camelCase JSON, the wire contract the web already reads."""
    return f"event: {kind}\ndata: {payload.model_dump_json(by_alias=True)}\n\n"


def _failure_of(exc: Exception) -> tuple[int, str]:
    """What a failed compile is, as one status and one sentence — for both entry points.

    The two entry points answer differently in *form* (a status with a detail, or a frame on a
    stream that has long since sent its status) but they are reporting the same failures, and a
    learner's report of one has to be recognisable as the other's. Deciding that twice is how the
    same exception comes to say "rephrase your topic" on one path and something else on the other —
    which is exactly the drift this codebase has already been bitten by once (AD6).
    """
    if isinstance(exc, TimeoutError):
        # Nothing was wrong with the topic, so retrying it verbatim is reasonable — which is why
        # this is distinct from the 502 below rather than folded in with it.
        return status.HTTP_504_GATEWAY_TIMEOUT, _TOO_SLOW
    if isinstance(exc, PersistenceError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE
    if isinstance(exc, GraphCompilationError):
        # The model gave us nothing usable. Say so — an empty graph would read to the learner as
        # "your topic has no concepts in it" rather than "we failed", and they would have no reason
        # to retry. 502: the failure is upstream of us, and trying again is worth doing.
        return status.HTTP_502_BAD_GATEWAY, _UNMAPPABLE
    # Something we did not anticipate. It reads as ours rather than as the topic's fault, because
    # telling a learner to rephrase a topic that was never the problem sends them in circles. The
    # await-full path re-raises on this instead, so an unexpected error keeps its traceback.
    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Something went wrong building this map. Try again.",
    )


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
