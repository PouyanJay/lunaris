from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.schema import Course

from ..dependencies import CourseServiceDep
from ..schemas import CourseRequest

router = APIRouter(prefix="/api/courses", tags=["courses"])


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


@router.get("/{course_id}", response_model=Course)
async def get_course(course_id: str, service: CourseServiceDep) -> Course:
    """Fetch a previously generated course-object by id."""
    course = service.get(course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course
