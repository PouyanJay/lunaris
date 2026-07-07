from uuid import uuid4

from fastapi import APIRouter, Response
from lunaris_runtime.logging import bind_request_id

from ..dependencies import OptionalUserIdDep, ProgressStoreDep
from ..schemas import LessonProgressView, ObjectiveProgressView, ProgressSnapshotView

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
    )
