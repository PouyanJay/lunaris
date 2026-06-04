from uuid import uuid4

from fastapi import APIRouter, Path, Query, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import CorpusServiceDep
from ..schemas import CorpusSourceView, CorpusTextRequest, IngestResultView

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


@router.post("/sources", response_model=IngestResultView, status_code=status.HTTP_201_CREATED)
async def add_text_source(
    payload: CorpusTextRequest, service: CorpusServiceDep, response: Response
) -> IngestResultView:
    """Add a pasted/plain-text source to a course's grounding corpus (P6.1 manual mode).

    Returns the gate's verdict (``accepted`` + the ``sourceId`` + chunk count, or a ``reason`` when
    declined). The generated ``request_id`` rides ``X-Request-Id`` for cross-layer log correlation.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    outcome = await service.add_text(
        course_id=payload.course_id, title=payload.title, text=payload.text
    )
    return IngestResultView.of(outcome)


@router.get("", response_model=list[CorpusSourceView])
async def list_sources(
    service: CorpusServiceDep,
    response: Response,
    course_id: str = Query(..., alias="courseId", min_length=1),
) -> list[CorpusSourceView]:
    """List a course's manually-ingested sources (one row per source), for the Corpus panel."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    summaries = await service.list_sources(course_id)
    return [CorpusSourceView.of(summary) for summary in summaries]


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    service: CorpusServiceDep, source_id: str = Path(..., pattern=r"^[0-9a-f]{32}$")
) -> Response:
    """Remove a source (all its chunks) from the corpus. Idempotent: 204 even if nothing matched."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    await service.delete_source(source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})
