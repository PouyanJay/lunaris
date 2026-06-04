from typing import Annotated, assert_never
from uuid import uuid4

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import CorpusServiceDep
from ..schemas import CorpusSourceRequest, CorpusSourceView, IngestResultView

router = APIRouter(prefix="/api/corpus", tags=["corpus"])

# Cap an uploaded file so a huge document can't exhaust memory at ingest time.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _bind() -> str:
    """Bind a fresh correlation id for the request and return it (for the X-Request-Id header)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    return request_id


@router.post("/sources", response_model=IngestResultView, status_code=status.HTTP_201_CREATED)
async def add_source(
    payload: CorpusSourceRequest, service: CorpusServiceDep, response: Response
) -> IngestResultView:
    """Add a pasted-text or URL source to a course's grounding corpus (P6.1 manual mode).

    Returns the gate's verdict (``accepted`` + ``sourceId`` + chunk count, or a ``reason`` when
    declined — e.g. a duplicate, or a URL that couldn't be fetched). ``X-Request-Id`` correlates.
    """
    response.headers["X-Request-Id"] = _bind()
    if payload.kind == "text":
        outcome = await service.add_text(
            course_id=payload.course_id, title=payload.title, text=payload.text or ""
        )
    elif payload.kind == "url":
        outcome = await service.add_url(course_id=payload.course_id, url=payload.url or "")
    else:  # the Literal kind is exhausted above; this pins exhaustiveness for a future kind.
        assert_never(payload.kind)
    return IngestResultView.of(outcome)


@router.post("/sources/file", response_model=IngestResultView, status_code=status.HTTP_201_CREATED)
async def add_file_source(
    service: CorpusServiceDep,
    response: Response,
    course_id: Annotated[str, Form(alias="courseId", min_length=1)],
    file: Annotated[UploadFile, File()],
) -> IngestResultView:
    """Add an uploaded document (PDF/DOCX/MD/TXT) to a course corpus; text is extracted first."""
    response.headers["X-Request-Id"] = _bind()
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        return IngestResultView(accepted=False, source_id="", chunks=0, reason="file too large")
    outcome = await service.add_file(
        course_id=course_id,
        filename=file.filename or "upload",
        content_type=file.content_type,
        data=data,
    )
    return IngestResultView.of(outcome)


@router.get("", response_model=list[CorpusSourceView])
async def list_sources(
    service: CorpusServiceDep,
    response: Response,
    course_id: str = Query(..., alias="courseId", min_length=1),
) -> list[CorpusSourceView]:
    """List a course's manually-ingested sources (one row per source), for the Corpus panel."""
    response.headers["X-Request-Id"] = _bind()
    summaries = await service.list_sources(course_id)
    return [CorpusSourceView.of(summary) for summary in summaries]


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    service: CorpusServiceDep, source_id: str = Path(..., pattern=r"^[0-9a-f]{32}$")
) -> Response:
    """Remove a source (all its chunks) from the corpus. Idempotent: 204 even if nothing matched."""
    request_id = _bind()
    await service.delete_source(source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})
