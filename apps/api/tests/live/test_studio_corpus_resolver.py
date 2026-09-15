"""The adapter reads only owned published course content and preserves immutable revisions."""

import threading
from typing import Any

import pytest
from lunaris_api.live.corpus.studio_resolver import StudioCorpusResolver
from lunaris_api.live.corpus.unavailable import CorpusUnavailableError
from lunaris_live.corpus.models.snapshot_key import SnapshotKey
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_runtime.schema import Course


def course_payload() -> dict[str, Any]:
    return {
        "id": "course-1",
        "topic": "Fixture course",
        "status": "published",
        "scopeNote": "Practice only.",
        "provenance": [{"id": "cite1", "title": "Reference", "url": "https://example.test/doc"}],
        "modules": [
            {
                "id": "m / unsafe",
                "title": "Privacy",
                "objectives": [
                    {
                        "statement": "Explain consent",
                        "bloomLevel": "understand",
                        "kc": "kc1",
                        "assessedBy": ["q1"],
                    }
                ],
                "lessons": [
                    {
                        "id": "lesson / unicode π",
                        "segments": {
                            "activate": {"prose": "Recall consent"},
                            "demonstrate": {
                                "prose": "Consent has a purpose.",
                                "claims": [
                                    {
                                        "text": "Consent has a purpose.",
                                        "supportedBy": "cite1",
                                        "verifierStatus": "supported",
                                    }
                                ],
                            },
                            "apply": {"prose": "Find the purpose"},
                            "integrate": {"prose": "Apply at work"},
                        },
                    }
                ],
                "assessment": {
                    "items": [
                        {
                            "id": "q1",
                            "prompt": "Explain consent",
                            "objective": "Explain consent",
                            "answer": "PRIVATE KEY",
                            "passCriterion": "State the purpose",
                        }
                    ]
                },
            }
        ],
    }


class _Courses:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.course: Course | None = Course.model_validate(payload or course_payload())
        self.reads: list[tuple[str, str | None, int]] = []

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        self.reads.append((course_id, owner_id, threading.get_ident()))
        if self.course is None or owner_id != "owner" or course_id != self.course.id:
            raise FileNotFoundError(course_id)
        return self.course


class _Snapshots:
    def __init__(self) -> None:
        self.rows: dict[SnapshotKey, CorpusSnapshot] = {}

    def save(self, snapshot: CorpusSnapshot, *, owner_id: str) -> CorpusSnapshot:
        key = SnapshotKey(
            owner_id=owner_id,
            course_id=snapshot.source.course_id,
            digest=snapshot.source.digest,
            adapter_version=snapshot.source.adapter_version,
            schema_version=snapshot.schema_version,
        )
        return self.rows.setdefault(key, snapshot)


async def test_normalized_content_provenance_private_answers_and_stable_digest() -> None:
    courses, snapshots = _Courses(), _Snapshots()
    resolver = StudioCorpusResolver(courses, snapshots)
    reference = CorpusReference(course_id="course-1")
    first = await resolver.resolve(reference, owner_id="owner", run_id="run1")
    assert len(first.sections) == 2
    lesson, assessment = first.sections
    assert "Consent has a purpose" in lesson.text
    assert lesson.objectives == ("Explain consent",)
    assert lesson.claims[0].citation_id == "cite1"
    assert first.citations[0].id == "cite1"
    assert first.caveats == ("Practice only.",)
    assert assessment.answer_key == "PRIVATE KEY"
    assert "PRIVATE KEY" not in assessment.text
    assert "PRIVATE KEY" not in first.source.model_dump_json()
    assert courses.reads[0][2] != threading.get_ident()
    courses.course.learner.goal = "other-learner"
    second = await resolver.resolve(reference, owner_id="owner", run_id="run2")
    assert second.source.digest == first.source.digest
    assert second.source.run_id == "run2"
    assert len(snapshots.rows) == 1
    assert next(iter(snapshots.rows.values())).source.run_id == "run1"
    courses.course.modules[0].lessons[0].segments.activate.prose = "Changed content"
    third = await resolver.resolve(reference, owner_id="owner", run_id="run3")
    assert third.source.digest != first.source.digest
    assert third.sections[0].locator == first.sections[0].locator
    assert len(snapshots.rows) == 2


@pytest.mark.parametrize(
    "owner,status",
    [("foreign", "published"), ("", "published"), ("owner", "review"), ("owner", "authoring")],
)
async def test_refuses_unowned_or_unpublished_source(owner: str, status: str) -> None:
    payload = course_payload()
    payload["status"] = status
    courses, snapshots = _Courses(payload), _Snapshots()
    with pytest.raises(CorpusUnavailableError):
        await StudioCorpusResolver(courses, snapshots).resolve(
            CorpusReference(course_id="course-1"), owner_id=owner, run_id="run"
        )
    assert not snapshots.rows


async def test_cached_snapshot_does_not_bypass_deleted_source() -> None:
    courses, snapshots = _Courses(), _Snapshots()
    resolver = StudioCorpusResolver(courses, snapshots)
    await resolver.resolve(CorpusReference(course_id="course-1"), owner_id="owner", run_id="run")
    courses.course = None
    with pytest.raises(CorpusUnavailableError):
        await resolver.resolve(
            CorpusReference(course_id="course-1"), owner_id="owner", run_id="again"
        )


@pytest.mark.parametrize("variant", ["empty", "oversize", "incomplete"])
async def test_unusable_sources_fail_explicitly(variant: str) -> None:
    payload = course_payload()
    if variant == "empty":
        payload["modules"] = []
    elif variant == "oversize":
        payload["modules"][0]["lessons"][0]["segments"]["activate"]["prose"] = "x" * 200001
    else:
        for segment in payload["modules"][0]["lessons"][0]["segments"].values():
            segment["prose"] = ""
        payload["modules"][0]["assessment"] = {"items": []}
    with pytest.raises(ValueError):
        await StudioCorpusResolver(_Courses(payload), _Snapshots()).resolve(
            CorpusReference(course_id="course-1"), owner_id="owner", run_id="run"
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.test/doc",
        "javascript:alert(1)",
        "https://example.test/doc?access_token=private",
        "https://example.test/doc?X-Goog-Signature=private",
    ],
)
async def test_rejects_credential_bearing_citation_references(url: str) -> None:
    payload = course_payload()
    payload["provenance"][0]["url"] = url
    from lunaris_api.live.corpus.invalid import CorpusInvalidError

    with pytest.raises(CorpusInvalidError):
        await StudioCorpusResolver(_Courses(payload), _Snapshots()).resolve(
            CorpusReference(course_id="course-1"), owner_id="owner", run_id="safe"
        )


async def test_store_cannot_substitute_another_course() -> None:
    courses = _Courses()
    original = courses.load

    def load(course_id: str, *, owner_id: str | None) -> Course:
        result = original(course_id, owner_id=owner_id)
        return result.model_copy(update={"id": "different"})

    courses.load = load
    with pytest.raises(CorpusUnavailableError):
        await StudioCorpusResolver(courses, _Snapshots()).resolve(
            CorpusReference(course_id="course-1"), owner_id="owner", run_id="safe"
        )
