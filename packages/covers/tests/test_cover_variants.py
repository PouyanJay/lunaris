"""Variant coverage for the cover pipeline (course-cover-images T11, the final task).

Parametrizes the pipeline over ALL three art-direction presets — the supported "modes" — asserting
each steers the art director and is recorded in provenance, and covers the cover-attach concurrency
posture (the worker re-reads the latest course, so a concurrent field change before the attach
survives alongside the cover). The precedence variants (keyed→image, keyless→Typographic,
failure→fallback, cancel, RLS owner-scoping) are exercised in the API + web suites; this is the
final parametric sweep the journey mandates.
"""

import base64

import pytest
from lunaris_covers import (
    CourseStoreCoverSourceProvider,
    CoverArtDirector,
    CoverPipeline,
    CoverWorker,
    OpenAiImageRenderer,
    StubCoverPipeline,
)
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_runtime.persistence import (
    InMemoryCoverJobQueue,
    InMemoryCoverStorage,
)
from lunaris_runtime.schema import (
    Course,
    CoverJob,
    CoverJobStatus,
    CoverStylePreset,
)

_OWNER = "u-1"
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _StubInvoke:
    def __init__(self, reply: str = "an amber motif on near-black") -> None:
        self.reply = reply
        self.prompt: str | None = None

    async def __call__(self, prompt: str) -> str:
        self.prompt = prompt
        return self.reply


class _FakeImagesClient:
    def __init__(self) -> None:
        self.images = self._Images()

    class _Images:
        async def generate(self, **kwargs: object) -> object:
            b64 = base64.b64encode(_PNG).decode("ascii")
            return type("Resp", (), {"data": [type("Datum", (), {"b64_json": b64})()]})()

        async def edit(self, **kwargs: object) -> object:
            # The dual-theme light re-theme seam — a distinct image derived from the dark render.
            b64 = base64.b64encode(_PNG + b"L").decode("ascii")
            return type("Resp", (), {"data": [type("Datum", (), {"b64_json": b64})()]})()


class _FakeCourseStore:
    def __init__(self) -> None:
        self._by_owner: dict[tuple[str | None, str], Course] = {}

    def seed(self, course: Course, *, owner_id: str) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._by_owner.get((owner_id, course_id))
        if course is None:
            raise FileNotFoundError(course_id)
        return course

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._by_owner.pop((owner_id, course_id), None) is not None


async def _noop_stage(_: CoverJobStatus) -> None:
    return None


@pytest.mark.parametrize(
    "preset",
    [CoverStylePreset.NOCTURNE, CoverStylePreset.BLUEPRINT, CoverStylePreset.AURORA],
)
@pytest.mark.asyncio
async def test_pipeline_covers_every_style_preset(preset: CoverStylePreset) -> None:
    store = _FakeCourseStore()
    store.seed(Course(id="c-1", topic="How HTTPS works"), owner_id=_OWNER)
    invoke = _StubInvoke()
    pipeline = CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=invoke, model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=_FakeImagesClient),
        qa_model="claude-opus-4-8",
    )
    job = CoverJob(id="job-1", user_id=_OWNER, course_id="c-1", input_hash="h", style_preset=preset)

    rendered = await pipeline.produce(job, on_stage=_noop_stage)

    # The chosen preset steers the art director AND is recorded in provenance.
    assert invoke.prompt is not None and preset.value in invoke.prompt.lower()
    assert rendered.provenance.style_preset is preset
    # Every preset yields a dual-theme cover: a light twin alongside the dark render (the light/dark
    # axis is orthogonal to the preset). No inspector here (local-dev path) → the re-theme is kept.
    assert rendered.image_light is not None and rendered.image_light != rendered.image
    assert rendered.provenance.has_light_variant is True
    assert rendered.provenance.light_mode == "retheme"


@pytest.mark.asyncio
async def test_cover_attach_reloads_the_course_instead_of_a_stale_snapshot() -> None:
    # The worker's attach re-reads the LATEST course rather than an earlier snapshot, so a course
    # field changed after the job was claimed (here the topic) survives alongside the new cover
    # (course-cover-images T11 concurrency AD). The residual true-concurrency race — a full-Course
    # save BETWEEN this load and save — is the documented systemic gap, out of scope here.
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    store = _FakeCourseStore()
    store.seed(Course(id="c-1", topic="Original topic"), owner_id=_OWNER)
    await queue.enqueue(CoverJob(id="job-1", user_id=_OWNER, course_id="c-1", input_hash="h"))

    # A stub pipeline that mutates the course (a concurrent writer) between claim and attach.
    class _MutatingPipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            current = store.load("c-1", owner_id=_OWNER)
            store.save(current.model_copy(update={"topic": "Edited topic"}), owner_id=_OWNER)
            return await StubCoverPipeline().produce(job, on_stage=on_stage)

    worker = CoverWorker(
        queue=queue,
        pipeline=_MutatingPipeline(),
        storage=storage,
        course_store=store,  # type: ignore[arg-type]
        worker_id="w",
    )

    assert await worker.run_once() is True

    course = store.load("c-1", owner_id=_OWNER)
    assert course.topic == "Edited topic"  # the concurrent change survived the cover attach
    assert course.cover is not None and course.cover.status is CoverJobStatus.READY
