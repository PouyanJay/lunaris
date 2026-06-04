from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.schema import AgentEvent, Clarification, Course, ProgressEvent
from pydantic import ValidationError

from ..dependencies import CourseServiceDep
from ..schemas import CourseRequest
from ..service import (
    CourseBuildCancelledError,
    CourseDeletionConflictError,
    CourseNotFoundError,
    InvalidCourseIdError,
    LessonRegenerationUnsupportedError,
)

router = APIRouter(prefix="/api/courses", tags=["courses"])

# The clarification rides the GET stream as a JSON query param (the web is fetch-based, and the
# payload is a handful of short fields). Capped so a malformed/oversized value can't bloat the URL.
_MAX_CLARIFICATION_CHARS = 4000


def _parse_clarification(raw: str | None) -> Clarification | None:
    """Parse the optional ``clarification`` query param (camelCase JSON) into the typed model.

    Blank/absent → ``None`` (the default one-click build). Malformed JSON is rejected at the
    boundary with a 422 rather than silently dropped, so a broken personalization surfaces.
    """
    if not raw:
        return None
    try:
        return Clarification.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid clarification"
        ) from exc


def _sse_frame(kind: str, payload: ProgressEvent | AgentEvent | Course) -> str:
    """Encode one stream item as an SSE frame (camelCase JSON, the web's wire contract)."""
    return f"event: {kind}\ndata: {payload.model_dump_json(by_alias=True)}\n\n"


@router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseRequest, service: CourseServiceDep, response: Response
) -> Course:
    """Run the pipeline for a topic and return the finished course-object (await_full).

    The generated ``run_id`` is returned in the ``X-Run-Id`` header so a single run can be
    triangulated across every layer's logs. 409 if the build is cancelled mid-flight.
    """
    course_id = uuid4().hex
    run_id = uuid4().hex
    response.headers["X-Run-Id"] = run_id
    try:
        return await service.create(
            payload.topic,
            course_id=course_id,
            run_id=run_id,
            clarification=payload.clarification,
        )
    except CourseBuildCancelledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Build was cancelled"
        ) from exc


@router.get("/stream")
async def stream_course(
    service: CourseServiceDep,
    topic: str = Query(min_length=1, max_length=200),
    clarification: str | None = Query(default=None, max_length=_MAX_CLARIFICATION_CHARS),
) -> StreamingResponse:
    """Run the pipeline for a topic and stream live build progress as Server-Sent Events.

    EventSource-compatible (GET + query param). Emits a ``progress`` event per pipeline
    stage as it happens, then a terminal ``course`` event carrying the finished
    camelCase course-object — so the web renders without a second fetch. The optional
    ``clarification`` query param carries the learner's opt-in confirm answers (P7.5) as
    camelCase JSON; absent, the build uses the interpreter's inference. The generated
    ``run_id`` is returned in ``X-Run-Id`` (sent before the body) for cross-layer
    correlation.
    """
    course_id = uuid4().hex
    run_id = uuid4().hex
    parsed_clarification = _parse_clarification(clarification)

    async def events() -> AsyncIterator[str]:
        async for kind, payload in service.stream(
            topic, course_id=course_id, run_id=run_id, clarification=parsed_clarification
        ):
            yield _sse_frame(kind, payload)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "X-Run-Id": run_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering so events flush live
        },
    )


@router.get("/{course_id}", response_model=Course)
async def get_course(course_id: str, service: CourseServiceDep) -> Course:
    """Fetch a previously generated course-object by id."""
    course = service.get(course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(course_id: str, service: CourseServiceDep) -> Response:
    """Delete a course and its per-course assets (the stored course-object + its run-history row).

    400 if the id isn't the safe shape; 409 if the run is still building (cancel it first); 404 if
    there's nothing to delete; 204 on success. A ``request_id`` is bound + returned in
    ``X-Request-Id`` so the deletion is traceable across the structured logs.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    headers = {"X-Request-Id": request_id}
    try:
        await service.delete_course(course_id)
    except InvalidCourseIdError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course id", headers=headers
        ) from exc
    except CourseDeletionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a course while its run is in progress; cancel it first",
            headers=headers,
        ) from exc
    except CourseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found", headers=headers
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@router.post("/{course_id}/lessons/{lesson_id}/regenerate", response_model=Course)
async def regenerate_lesson(
    course_id: str, lesson_id: str, service: CourseServiceDep, response: Response
) -> Course:
    """Re-author a single lesson with the agent and return the updated course-object.

    The new ``run_id`` is surfaced in ``X-Run-Id`` for cross-layer correlation. 404 if the course
    or lesson is unknown; 501 if the active pipeline can't regenerate a single lesson.
    """
    run_id = uuid4().hex
    response.headers["X-Run-Id"] = run_id
    try:
        course = await service.regenerate_lesson(course_id, lesson_id, run_id=run_id)
    except LessonRegenerationUnsupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="This pipeline does not support lesson regeneration",
        ) from exc
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course or lesson not found"
        )
    return course
