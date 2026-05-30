from typing import Annotated

from fastapi import Depends
from lunaris_agent import build_orchestrator, build_stub_orchestrator
from lunaris_runtime.persistence import CourseStore

from .config import Settings, get_settings
from .service import CourseService


def get_course_service(settings: Annotated[Settings, Depends(get_settings)]) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    store = CourseStore(settings.course_dir)
    factory = build_stub_orchestrator if settings.pipeline == "stub" else build_orchestrator
    return CourseService(store, factory)


CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]
