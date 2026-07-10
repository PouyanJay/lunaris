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
