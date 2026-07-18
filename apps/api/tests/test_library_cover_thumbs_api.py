"""Integration tests for pre-signed cover thumbnails on the library list (``GET /api/courses``).

The library used to ship only the bare cover HANDLE, so each card minted its own signed URL —
N follow-up ``GET /api/covers/{jobId}`` calls that resolved one by one (the "covers pop in one by
one" bug). These tests pin the fix: a READY cover's display-size ``thumbUrl`` (and its LIGHT twin
for a dual-theme cover) is minted server-side AT LIST TIME and rides on the summary, so the whole
grid arrives cover-ready in one request.

Traverses the real layers — HTTP → service → run index + course store → summary view → the cover
storage's ``signed_url`` — with the deterministic stub pipeline building the course and an
in-memory cover storage minting the URLs.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, auth_headers
from _doubles import CannotResizeCoverStorage
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_cover_storage, get_progress_store, get_run_store
from lunaris_api.progress import InMemoryProgressStore
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryCoverStorage,
    InMemoryRunStore,
    IRunStore,
)
from lunaris_runtime.schema import (
    CoverArtifact,
    CoverJobStatus,
    CoverLightMode,
    CoverProvenance,
    CoverStylePreset,
)

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_DEV_ORIGIN = "http://localhost:5173"


def _build_client(
    tmp_path: Path, run_store: IRunStore, cover_storage: InMemoryCoverStorage
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    # auth ON (a JWT secret) — an owned course, so cover paths are the real owner-scoped ones.
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(_DEV_ORIGIN,),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,
    )
    app.dependency_overrides[get_run_store] = lambda: run_store
    app.dependency_overrides[get_progress_store] = lambda: InMemoryProgressStore()
    app.dependency_overrides[get_cover_storage] = lambda: cover_storage
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
def cover_storage() -> InMemoryCoverStorage:
    return InMemoryCoverStorage()


@pytest.fixture
async def client(
    tmp_path: Path, run_store: InMemoryRunStore, cover_storage: InMemoryCoverStorage
) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, run_store, cover_storage) as http_client:
        yield http_client


def _provenance(course_id: str, *, has_light: bool) -> CoverProvenance:
    return CoverProvenance(
        job_id="cover-1",
        course_id=course_id,
        model="gpt-image-2",
        art_director_model="claude-opus",
        qa_model="claude-opus",
        style_preset=CoverStylePreset.GENERAL,
        prompt="an abstract constellation",
        input_hash="deadbeef",
        generated_at="2026-01-01T00:00:00Z",
        has_light_variant=has_light,
        light_mode=CoverLightMode.RETHEME if has_light else None,
    )


def _attach_cover(
    tmp_path: Path, course_id: str, *, status: CoverJobStatus, has_light: bool = False
) -> None:
    """Fold a cover artifact onto the persisted course payload the service reads at list time."""
    store = CourseStore(tmp_path)
    course = store.load(course_id, owner_id=USER_A)
    provenance = (
        _provenance(course_id, has_light=has_light) if status == CoverJobStatus.READY else None
    )
    updated = course.model_copy(
        update={"cover": CoverArtifact(status=status, job_id="cover-1", provenance=provenance)}
    )
    store.save(updated, owner_id=USER_A)


async def _build_course(client: httpx.AsyncClient, topic: str) -> str:
    created = await client.post("/api/courses", json={"topic": topic}, headers=auth_headers(USER_A))
    assert created.status_code == 201
    return created.json()["id"]


async def _summary(client: httpx.AsyncClient, course_id: str) -> dict:
    response = await client.get("/api/courses", headers=auth_headers(USER_A))
    assert response.status_code == 200
    return next(s for s in response.json() if s["id"] == course_id)


async def test_ready_cover_carries_a_signed_thumb_url_on_the_summary(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # Arrange — a built course with a READY dark-only cover.
    course_id = await _build_course(client, "binary search")
    _attach_cover(tmp_path, course_id, status=CoverJobStatus.READY)

    # Act
    response = await client.get("/api/courses", headers=auth_headers(USER_A))
    summary = next(s for s in response.json() if s["id"] == course_id)

    # Assert — the display-size thumb is signed at list time and rides on the summary (no per-card
    # /api/covers/{jobId} round trip), and the request id threads the logs.
    assert summary["thumbUrl"] is not None
    assert summary["thumbUrl"].startswith("memory://course-covers/")
    assert f"{course_id}/cover-1/cover.png" in summary["thumbUrl"]
    assert "width=1280" in summary["thumbUrl"]  # the COVER_DISPLAY_TRANSFORM — a resized derivative
    assert summary["thumbUrlLight"] is None  # dark-only cover: no light twin
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])


async def test_dual_theme_cover_carries_both_thumb_urls(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # Arrange — a READY cover whose provenance says a LIGHT twin exists.
    course_id = await _build_course(client, "binary search")
    _attach_cover(tmp_path, course_id, status=CoverJobStatus.READY, has_light=True)

    # Act
    summary = await _summary(client, course_id)

    # Assert — both variants are signed; the light one points at the second object.
    assert f"{course_id}/cover-1/cover.png" in summary["thumbUrl"]
    assert summary["thumbUrlLight"] is not None
    assert f"{course_id}/cover-1/cover-light.png" in summary["thumbUrlLight"]


async def test_course_without_a_cover_has_null_thumb_urls(client: httpx.AsyncClient) -> None:
    # Arrange — a plain built course (keyless / covers off): no cover handle at all.
    course_id = await _build_course(client, "binary search")

    # Act
    summary = await _summary(client, course_id)

    # Assert — nothing to sign; the card shows the Typographic fallback.
    assert summary["thumbUrl"] is None
    assert summary["thumbUrlLight"] is None


async def test_failed_cover_has_null_thumb_urls(client: httpx.AsyncClient, tmp_path: Path) -> None:
    # Arrange — a FAILED cover: it has a job_id (for regenerate) but no renderable image.
    course_id = await _build_course(client, "binary search")
    _attach_cover(tmp_path, course_id, status=CoverJobStatus.FAILED)

    # Act
    summary = await _summary(client, course_id)

    # Assert — only a READY cover mints a thumb; a failed one stays null (Typographic fallback).
    assert summary["thumbUrl"] is None
    assert summary["thumbUrlLight"] is None


async def test_thumb_degrades_to_null_when_storage_cannot_resize(tmp_path: Path) -> None:
    # Arrange — a READY cover, but the storage cannot mint the resized thumb.
    run_store = InMemoryRunStore()
    async with _build_client(tmp_path, run_store, CannotResizeCoverStorage()) as client:
        course_id = await _build_course(client, "binary search")
        _attach_cover(tmp_path, course_id, status=CoverJobStatus.READY)

        # Act
        summary = await _summary(client, course_id)

    # Assert — the thumb degrades to null (the card falls back to the master via the handle or the
    # Typographic cover), and — critically — the library read still succeeds with the course listed.
    assert summary["id"] == course_id
    assert summary["thumbUrl"] is None
    assert summary["thumbUrlLight"] is None
