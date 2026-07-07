from uuid import uuid4

from fastapi import APIRouter, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import CourseServiceDep, OptionalUserIdDep, ProgressStoreDep
from ..progress import derive_rollups
from ..schemas import (
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


@router.get("", response_model=ProgressSnapshotView)
async def get_progress(
    course_id: str,
    store: ProgressStoreDep,
    courses: CourseServiceDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> ProgressSnapshotView:
    """The caller's progress on a course: understood objectives + lesson states.

    A course the user never touched returns an empty snapshot (no 404 — progress rows are
    independent of the course payload). With auth on this is the caller's OWN progress; with auth
    off it's the single-user offline bucket.
    """
    response.headers["X-Request-Id"] = _bind()
    objectives, lessons = await store.snapshot(user_id=owner_id, course_id=course_id)
    course = courses.get(course_id, owner_id=owner_id)
    summary_view: ProgressSummaryView | None = None
    kc_mastery: dict[str, bool] = {}
    if course is not None:
        summary, kc_mastery = derive_rollups(course, objectives, lessons)
        summary_view = ProgressSummaryView(
            understood_count=summary.understood_count,
            objective_total=summary.objective_total,
            lessons_done=summary.lessons_done,
            lesson_total=summary.lesson_total,
            percent=summary.percent,
        )
    return ProgressSnapshotView(
        course_id=course_id,
        objectives=[
            ObjectiveProgressView(
                module_id=mark.module_id,
                objective_index=mark.objective_index,
                understood_at=mark.understood_at,
            )
            for mark in objectives
        ],
        lessons=[
            LessonProgressView(
                lesson_id=mark.lesson_id,
                state=mark.state,
                updated_at=mark.updated_at,
            )
            for mark in lessons
        ],
        summary=summary_view,
        kc_mastery=kc_mastery,
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
