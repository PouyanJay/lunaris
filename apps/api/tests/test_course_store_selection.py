"""The composition root picks the durable Postgres course store when Supabase is configured, and the
file-backed store otherwise — the same has_supabase selection the run/event stores use."""

from pathlib import Path

from lunaris_api.config import Settings
from lunaris_api.dependencies import get_course_service
from lunaris_api.run_registry import RunRegistry
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunEventStore,
    InMemoryRunStore,
    SupabaseCourseStore,
)


def _settings(*, supabase: bool) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=Path(".courses"),
        cors_origins=(),
        supabase_url="http://127.0.0.1:54321" if supabase else None,
        supabase_service_role_key="service-role-key" if supabase else None,
    )


def _service_for(settings: Settings):
    return get_course_service(
        settings=settings,
        run_store=InMemoryRunStore(),
        registry=RunRegistry(),
        event_store=InMemoryRunEventStore(),
    )


def test_uses_supabase_course_store_when_supabase_is_configured() -> None:
    service = _service_for(_settings(supabase=True))
    assert isinstance(service._store, SupabaseCourseStore)


def test_uses_file_course_store_without_supabase() -> None:
    service = _service_for(_settings(supabase=False))
    assert isinstance(service._store, CourseStore)
