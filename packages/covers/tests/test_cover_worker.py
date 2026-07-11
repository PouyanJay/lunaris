"""CoverWorker loop contract (course-cover-images T0, hardened after Phase 1 review).

Mirrors packages/video/tests/test_video_worker.py for the cover worker: the job_id binds into the
structlog correlation context while a job runs (the "Correlation everywhere" contract + this
journey's Task-0 goal — a cover triangulates across queue → worker → storage by run_id=job_id), a
render failure settles the job FAILED without the loop ever raising, and — the Phase-1-review fix —
a genuine backend failure while folding the cover onto the course leaves the job in-flight for the
lease sweep to requeue, never marking it READY with an unwritten Course.cover.
"""

import asyncio

import structlog
from lunaris_covers import CoverWorker, StubCoverPipeline
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_runtime.persistence import (
    InMemoryCoverJobQueue,
    InMemoryCoverStorage,
    PersistenceError,
)
from lunaris_runtime.schema import Course, CoverJob, CoverJobStatus, CoverLightMode

_OWNER = "u1"


class _FakeCourseStore:
    """Owner-scoped in-memory course store; ``fail_save`` makes ``save`` raise a backend error."""

    def __init__(self, *, fail_save: bool = False) -> None:
        self._by_owner: dict[tuple[str | None, str], Course] = {}
        self._fail_save = fail_save

    def seed(self, course: Course, *, owner_id: str) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        if self._fail_save:
            raise PersistenceError("course store unavailable")
        self._by_owner[(owner_id, course.id)] = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._by_owner.get((owner_id, course_id))
        if course is None:
            raise FileNotFoundError(course_id)
        return course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._by_owner.pop((owner_id, course_id), None) is not None


def _job(job_id: str = "job-1") -> CoverJob:
    return CoverJob(id=job_id, user_id=_OWNER, course_id="course-1", input_hash="h")


def _store() -> _FakeCourseStore:
    store = _FakeCourseStore()
    store.seed(Course(id="course-1", topic="How HTTP works"), owner_id=_OWNER)
    return store


def _worker(queue, storage, course_store, *, pipeline=None) -> CoverWorker:
    return CoverWorker(
        queue=queue,
        pipeline=pipeline or StubCoverPipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="worker-test",
    )


async def test_run_once_binds_the_job_id_into_log_context_while_working() -> None:
    # Arrange — a pipeline double that captures the structlog contextvars active DURING the job.
    captured: dict[str, object] = {}

    class _CapturingPipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            captured.update(structlog.contextvars.get_contextvars())
            return await StubCoverPipeline().produce(job, on_stage=on_stage)

    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _store(), pipeline=_CapturingPipeline())

    # Act
    await worker.run_once()

    # Assert — every log line inside the job carries the correlation id; cleared afterwards.
    assert captured.get("run_id") == "job-1"
    assert captured.get("worker_id") == "worker-test"
    assert captured.get("course_id") == "course-1"
    leftover = structlog.contextvars.get_contextvars()
    assert "run_id" not in leftover and "worker_id" not in leftover and "course_id" not in leftover


async def test_a_pipeline_failure_settles_the_job_failed_without_raising() -> None:
    # Arrange — a render that explodes with an internal detail that must NOT reach the job row.
    class _ExplodingPipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            raise RuntimeError("openai exploded: sk-secret-abc leaked")

    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _store(), pipeline=_ExplodingPipeline())

    # Act — the loop never raises (its contract), even on a job-level failure.
    assert await worker.run_once() is True

    # Assert — settled FAILED with an owner-safe reason; the internal detail stayed in the logs.
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.FAILED
    assert job.error is not None
    assert "sk-secret-abc" not in job.error
    assert "RuntimeError" in job.error


async def test_a_pipeline_error_with_user_detail_settles_that_reason_on_the_job() -> None:
    # The actionable-failure contract (general-template-fidelity review): a CoverPipelineError's
    # user_detail — e.g. the art director exhausting its fields parse-repair budget — lands on the
    # job row verbatim, so the owner sees "couldn't write the cover's descriptive fields" instead
    # of a raw exception class name.
    from lunaris_covers.errors import CoverPipelineError

    class _DetailedFailurePipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            raise CoverPipelineError(
                "general cover fields did not parse after repair turns",
                user_detail="couldn't write the cover's descriptive fields",
            )

    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _store(), pipeline=_DetailedFailurePipeline())

    assert await worker.run_once() is True

    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.FAILED
    assert job.error == "couldn't write the cover's descriptive fields"


async def test_an_attach_backend_failure_leaves_the_job_in_flight_for_requeue() -> None:
    # Arrange — produce + upload succeed, but folding Course.cover hits a backend failure. The job
    # must NOT be marked READY (its Course.cover never got written) — it stays in-flight so the
    # lease sweep requeues it (at-least-once), honouring the "never silently wrong" invariant.
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _store_that_fails_save())

    # Act — run_once absorbs the propagated PersistenceError (logs job_unsettled), never raises.
    assert await worker.run_once() is True

    # Assert — the job is NOT READY (left in-flight at its last stage), so a sweep will requeue it.
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status != CoverJobStatus.READY
    assert job.status != CoverJobStatus.FAILED  # an infra failure is not a render failure
    # The image did upload (the failure was only the course-payload fold), so a requeue re-attaches.
    assert any(p.endswith("/cover.png") for p in storage.paths())


async def test_a_deleted_course_mid_generation_is_a_benign_skip() -> None:
    # Arrange — the course is gone by the time the cover settles (the owner deleted it). The image
    # still uploaded; the job settles READY (nothing to attach to), never FAILED.
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _FakeCourseStore())  # empty store → load raises FileNotFound

    # Act
    assert await worker.run_once() is True

    # Assert — READY despite the missing course (benign skip), image uploaded.
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.READY


async def test_concurrent_run_once_calls_each_claim_a_distinct_job() -> None:
    # Two workers draining the same queue never double-process a job (the claim's SKIP LOCKED
    # analogue in the in-memory lock).
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    course_store = _store()
    await queue.enqueue(_job("job-1"))
    course_store.seed(Course(id="course-2", topic="t2"), owner_id=_OWNER)
    await queue.enqueue(CoverJob(id="job-2", user_id=_OWNER, course_id="course-2", input_hash="h"))
    a = _worker(queue, storage, course_store, pipeline=StubCoverPipeline())
    b = _worker(queue, storage, course_store, pipeline=StubCoverPipeline())

    await asyncio.gather(a.run_once(), b.run_once())

    assert (await queue.get(job_id="job-1")).status == CoverJobStatus.READY  # type: ignore[union-attr]
    assert (await queue.get(job_id="job-2")).status == CoverJobStatus.READY  # type: ignore[union-attr]


async def test_a_dual_theme_cover_uploads_both_the_dark_and_light_images() -> None:
    # Arrange — a pipeline that produced BOTH a dark and a light image (a dual-theme cover). The
    # worker must upload both objects so the reader can show the light one in dark theme.
    class _DualThemePipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            base = await StubCoverPipeline().produce(job, on_stage=on_stage)
            return RenderedCover(
                image=base.image,
                image_light=base.image + b"L",
                provenance=base.provenance.model_copy(
                    update={"has_light_variant": True, "light_mode": CoverLightMode.RETHEME}
                ),
            )

    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, _store(), pipeline=_DualThemePipeline())

    # Act
    assert await worker.run_once() is True

    # Assert — the job is READY and BOTH images landed in the bucket under the job's path.
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.READY
    paths = storage.paths()
    assert any(p.endswith("/cover.png") for p in paths)
    assert any(p.endswith("/cover-light.png") for p in paths)


class _LightUploadFailsStorage:
    """Wraps InMemoryCoverStorage but fails the LIGHT image upload — the dark image and provenance
    still land. Proves a light-upload blip never sinks an already-stored dark cover (AD2 at the
    storage layer): the job settles READY dark-only, and the persisted provenance is downgraded."""

    def __init__(self) -> None:
        self._inner = InMemoryCoverStorage()

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None:
        if path.endswith("/cover-light.png"):
            raise PersistenceError("light upload boom")
        await self._inner.upload(path=path, data=data, content_type=content_type)

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        return await self._inner.signed_url(path=path, expires_in_seconds=expires_in_seconds)

    async def download(self, *, path: str) -> bytes:
        return await self._inner.download(path=path)

    async def delete(self, *, paths: list[str]) -> None:
        await self._inner.delete(paths=paths)

    def paths(self) -> list[str]:
        return self._inner.paths()

    def read(self, path: str) -> bytes:
        return self._inner.read(path)


async def test_a_failed_light_upload_still_ships_a_dark_only_cover() -> None:
    # Arrange — a dual-theme cover, but the LIGHT image upload fails. The dark image already landed,
    # so the job must settle READY dark-only (not FAILED), with the persisted + attached provenance
    # downgraded to has_light_variant=False so what's recorded matches what's in the bucket.
    class _DualThemePipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            base = await StubCoverPipeline().produce(job, on_stage=on_stage)
            return RenderedCover(
                image=base.image,
                image_light=base.image + b"L",
                provenance=base.provenance.model_copy(
                    update={"has_light_variant": True, "light_mode": CoverLightMode.RETHEME}
                ),
            )

    queue, storage = InMemoryCoverJobQueue(), _LightUploadFailsStorage()
    course_store = _store()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, course_store, pipeline=_DualThemePipeline())

    # Act
    assert await worker.run_once() is True

    # Assert — READY (not FAILED); the dark image + provenance landed, the light image did not.
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.READY
    paths = storage.paths()
    assert any(p.endswith("/cover.png") for p in paths)
    assert not any(p.endswith("/cover-light.png") for p in paths)
    # The provenance folded onto the course is downgraded to dark-only (matches the bucket).
    course = course_store.load("course-1", owner_id=_OWNER)
    assert course.cover is not None
    assert course.cover.provenance is not None
    assert course.cover.provenance.has_light_variant is False
    assert course.cover.provenance.light_mode is None


def _store_that_fails_save() -> _FakeCourseStore:
    store = _FakeCourseStore(fail_save=True)
    store.seed(Course(id="course-1", topic="How HTTP works"), owner_id=_OWNER)
    return store
