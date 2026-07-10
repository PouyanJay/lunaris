"""Real cover pipeline contract (course-cover-images T4): source → art director → GPT Image 2.

The pipeline is exercised end to end with the two *network* seams faked — a stub ``TextInvoke`` in
place of Claude and a fake OpenAI Images client in place of GPT Image 2 — so the real source
provider, art director, renderer and provenance-stamping all run. The assertions are the T4
contract: the art director sees the course topic + concept graph, the image model is asked with the
art director's exact prompt, and ``CoverProvenance`` is populated at the source (not just that image
bytes came back).
"""

import base64

import pytest
from lunaris_covers.art_direction.cover_art_director import CoverArtDirector
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.pipeline.cover_pipeline import CoverPipeline
from lunaris_covers.rendering.openai_image_renderer import OpenAiImageRenderer
from lunaris_covers.sourcing.course_store_cover_source_provider import (
    CourseStoreCoverSourceProvider,
)
from lunaris_runtime.schema import (
    Course,
    CoverJob,
    CoverJobStatus,
    CoverStylePreset,
    Edge,
    KnowledgeComponent,
    PrerequisiteGraph,
)

_OWNER = "u-1"
# A 1x1 PNG — enough to prove real image bytes flow through the renderer without a real render.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _StubArtDirectorInvoke:
    """A fake ``TextInvoke``: records the prompt Claude was handed, returns a canned art brief."""

    def __init__(
        self, reply: str = "A lone amber lighthouse over a near-black sea, vast sky."
    ) -> None:
        self.reply = reply
        self.prompt: str | None = None

    async def __call__(self, prompt: str) -> str:
        self.prompt = prompt
        return self.reply


class _FakeImagesClient:
    """A fake OpenAI client exposing just ``images.generate``, recording its kwargs."""

    def __init__(self, *, png: bytes = _PNG) -> None:
        self._png = png
        self.kwargs: dict[str, object] = {}
        self.images = self._Images(self)

    class _Images:
        def __init__(self, outer: "_FakeImagesClient") -> None:
            self._outer = outer

        async def generate(self, **kwargs: object) -> object:
            self._outer.kwargs = kwargs
            b64 = base64.b64encode(self._outer._png).decode("ascii")
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


def _course() -> Course:
    graph = PrerequisiteGraph(
        nodes=[
            KnowledgeComponent(
                id="k1", label="TCP handshake", definition="", difficulty=0.4, bloom_ceiling="apply"
            ),
            KnowledgeComponent(
                id="k2",
                label="TLS encryption",
                definition="",
                difficulty=0.6,
                bloom_ceiling="apply",
            ),
        ],
        edges=[Edge(**{"from": "k1", "to": "k2", "strength": 0.8})],
        topo_order=["k1", "k2"],
    )
    return Course(id="c-1", topic="How HTTPS works", graph=graph, scope_note="curious engineers")


def _job(preset: CoverStylePreset = CoverStylePreset.NOCTURNE) -> CoverJob:
    return CoverJob(
        id="job-1", user_id=_OWNER, course_id="c-1", input_hash="h-1", style_preset=preset
    )


async def _noop_stage(_: CoverJobStatus) -> None:
    return None


def _pipeline(
    store: _FakeCourseStore, invoke: _StubArtDirectorInvoke, client: _FakeImagesClient
) -> CoverPipeline:
    return CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=invoke, model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=lambda: client),
        qa_model="claude-opus-4-8",
    )


@pytest.mark.asyncio
async def test_produce_returns_rendered_cover_with_populated_provenance() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _StubArtDirectorInvoke()
    client = _FakeImagesClient()

    rendered = await _pipeline(store, invoke, client).produce(_job(), on_stage=_noop_stage)

    assert rendered.image == _PNG
    prov = rendered.provenance
    assert prov.source == "openai"
    assert prov.model == "gpt-image-2"
    assert prov.art_director_model == "claude-opus-4-8"
    assert prov.qa_model == "claude-opus-4-8"
    assert prov.style_preset is CoverStylePreset.NOCTURNE
    assert prov.prompt == invoke.reply  # the exact art-direction prompt is provenance
    assert prov.qa_attempts == 1
    assert prov.input_hash == "h-1"
    assert prov.generated_at  # ISO-8601 instant stamped at the source


@pytest.mark.asyncio
async def test_art_director_sees_topic_and_concept_graph() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _StubArtDirectorInvoke()

    await _pipeline(store, invoke, _FakeImagesClient()).produce(_job(), on_stage=_noop_stage)

    assert invoke.prompt is not None
    assert "How HTTPS works" in invoke.prompt
    assert "TCP handshake" in invoke.prompt
    assert "TLS encryption" in invoke.prompt


@pytest.mark.asyncio
async def test_image_model_is_asked_with_the_art_directors_prompt_at_high_quality() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _StubArtDirectorInvoke(reply="An amber orbit line around a dark planet.")
    client = _FakeImagesClient()

    await _pipeline(store, invoke, client).produce(_job(), on_stage=_noop_stage)

    assert client.kwargs["model"] == "gpt-image-2"
    assert client.kwargs["prompt"] == "An amber orbit line around a dark planet."
    assert client.kwargs["quality"] == "high"


@pytest.mark.asyncio
async def test_style_preset_steers_the_art_direction_prompt() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _StubArtDirectorInvoke()

    await _pipeline(store, invoke, _FakeImagesClient()).produce(
        _job(CoverStylePreset.BLUEPRINT), on_stage=_noop_stage
    )

    assert invoke.prompt is not None
    assert "blueprint" in invoke.prompt.lower()


@pytest.mark.asyncio
async def test_stages_are_reported_in_order() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    stages: list[CoverJobStatus] = []

    async def record(stage: CoverJobStatus) -> None:
        stages.append(stage)

    await _pipeline(store, _StubArtDirectorInvoke(), _FakeImagesClient()).produce(
        _job(), on_stage=record
    )

    assert stages == [CoverJobStatus.ART_DIRECTING, CoverJobStatus.RENDERING]


@pytest.mark.asyncio
async def test_missing_course_raises_cover_pipeline_error() -> None:
    store = _FakeCourseStore()  # nothing seeded
    with pytest.raises(CoverPipelineError):
        await _pipeline(store, _StubArtDirectorInvoke(), _FakeImagesClient()).produce(
            _job(), on_stage=_noop_stage
        )
