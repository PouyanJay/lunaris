"""course-cover-images T2: the cover artifact + provenance ride on the course payload in camelCase,
so the web TS mirror (`Course.cover` / `CoverArtifact` / `CoverProvenance`) matches the wire byte
for byte. Also asserts the fallback shape: a course without a cover serialises `cover: null`."""

import json

from lunaris_runtime.schema import (
    Course,
    CoverArtifact,
    CoverJobStatus,
    CoverProvenance,
    CoverStylePreset,
)


def _provenance() -> CoverProvenance:
    return CoverProvenance(
        job_id="job-1",
        course_id="course-1",
        model="gpt-image-2",
        art_director_model="claude-opus-4-8",
        qa_model="claude-opus-4-8",
        style_preset=CoverStylePreset.NOCTURNE,
        prompt="a lone lighthouse over a dark sea",
        qa_attempts=2,
        input_hash="h",
        generated_at="2026-07-10T00:00:00+00:00",
    )


def test_course_cover_serialises_camelcase_on_the_wire() -> None:
    course = Course(
        id="course-1",
        topic="How HTTP works",
        cover=CoverArtifact(status=CoverJobStatus.READY, job_id="job-1", provenance=_provenance()),
    )

    wire = json.loads(course.model_dump_json(by_alias=True))

    cover = wire["cover"]
    assert cover["status"] == "ready"
    assert cover["jobId"] == "job-1"  # camelCase, matching apps/web CoverArtifact
    prov = cover["provenance"]
    assert prov["artDirectorModel"] == "claude-opus-4-8"
    assert prov["qaModel"] == "claude-opus-4-8"
    assert prov["stylePreset"] == "nocturne"
    assert prov["qaAttempts"] == 2
    assert prov["source"] == "openai"  # the default provider literal
    assert prov["generatedAt"] == "2026-07-10T00:00:00+00:00"


def test_course_without_a_cover_serialises_null() -> None:
    course = Course(id="course-1", topic="How HTTP works")
    wire = json.loads(course.model_dump_json(by_alias=True))
    assert wire["cover"] is None  # the reader falls back to Typographic / constellation


def test_cover_artifact_round_trips_by_alias() -> None:
    artifact = CoverArtifact(status=CoverJobStatus.READY, job_id="job-1", provenance=_provenance())
    reloaded = CoverArtifact.model_validate_json(artifact.model_dump_json(by_alias=True))
    assert reloaded == artifact


def test_dual_theme_provenance_serialises_the_light_fields() -> None:
    prov = _provenance().model_copy(update={"has_light_variant": True, "light_mode": "retheme"})
    wire = json.loads(prov.model_dump_json(by_alias=True))
    assert wire["hasLightVariant"] is True
    assert wire["lightMode"] == "retheme"


def test_old_provenance_without_light_fields_defaults_to_dark_only() -> None:
    # A cover made before dual-theme: its persisted provenance JSON has no light fields. It must
    # still parse — defaulting to has_light_variant=False (dark-only, shown in both app themes) —
    # so existing covers keep working with no migration.
    old = _provenance().model_dump(by_alias=True)
    old.pop("hasLightVariant", None)
    old.pop("lightMode", None)

    reloaded = CoverProvenance.model_validate_json(json.dumps(old))

    assert reloaded.has_light_variant is False
    assert reloaded.light_mode is None


def test_cover_artifact_paths_include_a_light_image() -> None:
    from lunaris_runtime.persistence import CoverArtifactPaths

    paths = CoverArtifactPaths.for_coordinates("u-1", "course-1", "job-1")
    assert paths.image == "u-1/course-1/job-1/cover.png"  # the dark image keeps the original path
    assert paths.image_light == "u-1/course-1/job-1/cover-light.png"
    assert paths.provenance == "u-1/course-1/job-1/provenance.json"


def test_cover_job_serialises_camelcase_on_the_wire() -> None:
    # CoverJob rides on CoverJobView.job — lock its camelCase aliases so the web CoverJob* types
    # (which read jobs off the status endpoint) stay in step with the runtime schema.
    from datetime import UTC, datetime

    from lunaris_runtime.schema import CoverJob

    job = CoverJob(
        id="job-1",
        user_id="u-1",
        course_id="course-1",
        style_preset=CoverStylePreset.BLUEPRINT,
        input_hash="h",
        claimed_at=datetime(2026, 7, 10, tzinfo=UTC),
    )
    wire = json.loads(job.model_dump_json(by_alias=True))
    assert wire["userId"] == "u-1"
    assert wire["courseId"] == "course-1"
    assert wire["stylePreset"] == "blueprint"
    assert wire["inputHash"] == "h"
    assert wire["claimedAt"].startswith("2026-07-10")
    assert wire["status"] == "queued"
