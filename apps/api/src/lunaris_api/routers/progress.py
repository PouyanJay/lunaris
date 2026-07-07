import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import CourseServiceDep, OptionalUserIdDep, ProgressStoreDep
from ..progress import (
    LessonMark,
    ObjectiveMark,
    ProgressStoreUnavailableError,
    ProgressSummary,
    derive_rollups,
)
from ..schemas import (
    CourseOpenedRequest,
    LessonMarkRequest,
    LessonProgressView,
    ObjectiveMarkRequest,
    ObjectiveProgressView,
    ProgressSnapshotView,
    ProgressSummaryView,
)

router = APIRouter(prefix="/api/courses/{course_id}/progress", tags=["progress"])


def _bind() -> str:
    """Bind a fresh correlation id for the request and return it (for the X-Request-Id header)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    return request_id


def _objective_view(mark: ObjectiveMark) -> ObjectiveProgressView:
    return ObjectiveProgressView(
        module_id=mark.module_id,
        objective_index=mark.objective_index,
        understood_at=mark.understood_at,
    )


def _lesson_view(mark: LessonMark) -> LessonProgressView:
    return LessonProgressView(
        lesson_id=mark.lesson_id, state=mark.state, updated_at=mark.updated_at
    )


def _summary_view(summary: ProgressSummary) -> ProgressSummaryView:
    return ProgressSummaryView(
        understood_count=summary.understood_count,
        objective_total=summary.objective_total,
        lessons_done=summary.lessons_done,
        lesson_total=summary.lesson_total,
        percent=summary.percent,
    )


_UNAVAILABLE = "Progress is temporarily unavailable"


@router.get("", response_model=ProgressSnapshotView)
async def get_progress(
    course_id: str,
    store: ProgressStoreDep,
    courses: CourseServiceDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> ProgressSnapshotView:
    """The caller's progress on a course: understood objectives + lesson states + when/where the
    course was last opened.

    A course the user never touched returns an empty snapshot (no 404 — progress rows are
    independent of the course payload). With auth on this is the caller's OWN progress; with auth
    off it's the single-user offline bucket. A progress-backend outage is a recoverable 503 (kept
    inside the CORS middleware), never a raw 500.
    """
    response.headers["X-Request-Id"] = _bind()
    try:
        (objectives, lessons), state = await asyncio.gather(
            store.snapshot(user_id=owner_id, course_id=course_id),
            store.course_state(user_id=owner_id, course_id=course_id),
        )
    except ProgressStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNAVAILABLE
        ) from exc
    course = courses.get(course_id, owner_id=owner_id)
    summary_view: ProgressSummaryView | None = None
    kc_mastery: dict[str, bool] = {}
    if course is not None:
        summary, kc_mastery = derive_rollups(course, objectives, lessons)
        summary_view = _summary_view(summary)
    return ProgressSnapshotView(
        course_id=course_id,
        objectives=[_objective_view(mark) for mark in objectives],
        lessons=[_lesson_view(mark) for mark in lessons],
        summary=summary_view,
        kc_mastery=kc_mastery,
        last_opened_at=state.last_opened_at if state else None,
        last_lesson_id=state.last_lesson_id if state else None,
    )


@router.put("/objective", status_code=status.HTTP_204_NO_CONTENT)
async def put_objective(
    course_id: str,
    payload: ObjectiveMarkRequest,
    store: ProgressStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> None:
    """Mark or un-mark one module objective as understood (idempotent either way)."""
    response.headers["X-Request-Id"] = _bind()
    await store.set_objective(
        user_id=owner_id,
        course_id=course_id,
        module_id=payload.module_id,
        objective_index=payload.objective_index,
        understood=payload.understood,
    )


@router.put("/lesson", status_code=status.HTTP_204_NO_CONTENT)
async def put_lesson(
    course_id: str,
    payload: LessonMarkRequest,
    store: ProgressStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> None:
    """Advance a lesson's learner state — in_progress on first open, done on completion."""
    response.headers["X-Request-Id"] = _bind()
    await store.set_lesson(
        user_id=owner_id,
        course_id=course_id,
        lesson_id=payload.lesson_id,
        state=payload.state,
    )


@router.put("/opened", status_code=status.HTTP_204_NO_CONTENT)
async def put_opened(
    course_id: str,
    payload: CourseOpenedRequest,
    store: ProgressStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> None:
    """Record that the learner opened this course — optionally at a lesson (the reader's
    position). Idempotent upsert; a bare touch preserves any previously recorded position. A
    progress-backend outage is a recoverable 503 (kept inside the CORS middleware)."""
    response.headers["X-Request-Id"] = _bind()
    try:
        await store.touch_course(
            user_id=owner_id, course_id=course_id, last_lesson_id=payload.last_lesson_id
        )
    except ProgressStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNAVAILABLE
        ) from exc
