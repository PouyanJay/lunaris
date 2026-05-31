from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from lunaris_runtime.schema import Course, ProgressEvent

from ..dependencies import CourseServiceDep
from ..schemas import CourseRequest
from ..service import LessonRegenerationUnsupportedError

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _sse_frame(kind: str, payload: ProgressEvent | Course) -> str:
    """Encode one stream item as an SSE frame (camelCase JSON, the web's wire contract)."""
    return f"event: {kind}\ndata: {payload.model_dump_json(by_alias=True)}\n\n"


@router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseRequest, service: CourseServiceDep, response: Response
) -> Course:
    """Run the pipeline for a topic and return the finished course-object (await_full).

    The generated ``run_id`` is returned in the ``X-Run-Id`` header so a single run can be
    triangulated across every layer's logs.
    """
    course_id = uuid4().hex
    run_id = uuid4().hex
    response.headers["X-Run-Id"] = run_id
    return await service.create(payload.topic, course_id=course_id, run_id=run_id)


@router.get("/stream")
async def stream_course(
    service: CourseServiceDep,
    topic: str = Query(min_length=1, max_length=200),
) -> StreamingResponse:
    """Run the pipeline for a topic and stream live build progress as Server-Sent Events.

    EventSource-compatible (GET + query param). Emits a ``progress`` event per pipeline
    stage as it happens, then a terminal ``course`` event carrying the finished
    camelCase course-object — so the web renders without a second fetch. The generated
    ``run_id`` is returned in ``X-Run-Id`` (sent before the body) for cross-layer
    correlation.
    """
    course_id = uuid4().hex
    run_id = uuid4().hex

    async def events() -> AsyncIterator[str]:
        async for kind, payload in service.stream(topic, course_id=course_id, run_id=run_id):
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
