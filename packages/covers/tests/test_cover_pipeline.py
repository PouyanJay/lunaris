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
from lunaris_covers.schemas.cover_qa_verdict import CoverQaDefect, CoverQaVerdict
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


def _b64_resp(image: bytes) -> object:
    b64 = base64.b64encode(image).decode("ascii")
    return type("Resp", (), {"data": [type("Datum", (), {"b64_json": b64})()]})()


class _FakeImagesClient:
    """A fake OpenAI client exposing ``images.generate`` + ``images.edit``, recording their kwargs.

    ``edit`` is the composition-preserving re-theme seam (dual-theme covers): it returns a distinct
    PNG (the dark bytes with a ``L`` marker appended) so a test can prove the light variant is a
    different image derived from the dark render.
    """

    def __init__(self, *, png: bytes = _PNG) -> None:
        self._png = png
        self.kwargs: dict[str, object] = {}
        self.edit_kwargs: dict[str, object] = {}
        self.images = self._Images(self)

    class _Images:
        def __init__(self, outer: "_FakeImagesClient") -> None:
            self._outer = outer

        async def generate(self, **kwargs: object) -> object:
            self._outer.kwargs = kwargs
            return _b64_resp(self._outer._png)

        async def edit(self, **kwargs: object) -> object:
            self._outer.edit_kwargs = kwargs
            return _b64_resp(self._outer._png + b"L")


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


# ---- T5: vision-QA gate + bounded regenerate loop -------------------------------------------


class _RecordingArtInvoke:
    """A ``TextInvoke`` returning a distinct reply per call, recording every prompt it saw."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"art brief #{len(self.prompts)}"


class _ScriptedInspector:
    """A fake ``ICoverVisionQa`` that fails its first ``fail_first`` inspections, then passes.

    Records the images it inspected so a test can prove the loop re-renders (a fresh image per QA
    round), not just re-inspects the same bytes.
    """

    def __init__(self, *, fail_first: int) -> None:
        self._fail_first = fail_first
        self.calls = 0
        self.images: list[bytes] = []
        self.model = "claude-opus-4-8"

    async def inspect(self, image: bytes, brief: object) -> CoverQaVerdict:
        self.calls += 1
        self.images.append(image)
        if self.calls <= self._fail_first:
            return CoverQaVerdict(
                passed=False, defects=[CoverQaDefect(issue=f"defect round {self.calls}")]
            )
        return CoverQaVerdict(passed=True)


class _CountingImagesClient:
    """Like ``_FakeImagesClient`` but returns a distinct PNG per render (round in the last byte)."""

    def __init__(self) -> None:
        self.renders = 0
        self.edits = 0
        self.images = self._Images(self)

    class _Images:
        def __init__(self, outer: "_CountingImagesClient") -> None:
            self._outer = outer

        async def generate(self, **kwargs: object) -> object:
            self._outer.renders += 1
            return _b64_resp(_PNG + bytes([self._outer.renders]))

        async def edit(self, **kwargs: object) -> object:
            self._outer.edits += 1
            return _b64_resp(_PNG + b"L" + bytes([self._outer.edits]))


def _qa_pipeline(
    store: _FakeCourseStore,
    invoke: _RecordingArtInvoke,
    client: _CountingImagesClient,
    inspector: _ScriptedInspector,
    *,
    max_attempts: int = 3,
) -> CoverPipeline:
    return CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=invoke, model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=lambda: client),
        qa_model="claude-opus-4-8",
        inspector=inspector,
        max_attempts=max_attempts,
    )


@pytest.mark.asyncio
async def test_passing_first_qa_round_records_one_attempt() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _RecordingArtInvoke()
    inspector = _ScriptedInspector(fail_first=0)

    rendered = await _qa_pipeline(store, invoke, _CountingImagesClient(), inspector).produce(
        _job(), on_stage=_noop_stage
    )

    assert rendered.provenance.qa_attempts == 1
    assert len(invoke.prompts) == 1  # no regenerate needed
    assert inspector.calls == 1


@pytest.mark.asyncio
async def test_failed_qa_regenerates_with_defect_feedback_then_passes() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _RecordingArtInvoke()
    client = _CountingImagesClient()
    inspector = _ScriptedInspector(fail_first=1)  # fail once, pass on the retry

    rendered = await _qa_pipeline(store, invoke, client, inspector).produce(
        _job(), on_stage=_noop_stage
    )

    assert rendered.provenance.qa_attempts == 2
    assert len(invoke.prompts) == 2  # art-directed twice
    assert "defect round 1" in invoke.prompts[1]  # the retry brief carries the QA defect
    assert client.renders == 2  # a fresh render per round
    assert inspector.images[0] != inspector.images[1]  # QA saw the new image, not the old bytes
    # The image returned is the one that passed (the second render).
    assert rendered.image == inspector.images[1]


@pytest.mark.asyncio
async def test_exhausting_attempts_raises_rather_than_shipping_slop() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _RecordingArtInvoke()
    inspector = _ScriptedInspector(fail_first=99)  # never passes

    with pytest.raises(CoverPipelineError):
        await _qa_pipeline(
            store, invoke, _CountingImagesClient(), inspector, max_attempts=3
        ).produce(_job(), on_stage=_noop_stage)

    assert inspector.calls == 3  # bounded — exactly max_attempts rounds, no more


@pytest.mark.asyncio
async def test_qa_stage_is_reported() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    stages: list[CoverJobStatus] = []

    async def record(stage: CoverJobStatus) -> None:
        stages.append(stage)

    await _qa_pipeline(
        store, _RecordingArtInvoke(), _CountingImagesClient(), _ScriptedInspector(fail_first=0)
    ).produce(_job(), on_stage=record)

    assert stages == [
        CoverJobStatus.ART_DIRECTING,
        CoverJobStatus.RENDERING,
        CoverJobStatus.QA,
    ]


# ---- dual-theme: a light variant re-themed from the dark render ------------------------------


@pytest.mark.asyncio
async def test_produce_also_renders_a_light_variant_via_image_edit() -> None:
    # A dual-theme cover: after the dark render, the pipeline re-themes THAT render to a light
    # palette via the image-edit seam, so the course gets both a dark and a light image of the same
    # cover. Provenance records that a light variant exists and how it was produced.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    invoke = _StubArtDirectorInvoke()
    client = _FakeImagesClient()

    rendered = await _pipeline(store, invoke, client).produce(_job(), on_stage=_noop_stage)

    assert rendered.image == _PNG  # the dark render (the base) is unchanged
    assert rendered.image_light is not None
    assert rendered.image_light != rendered.image  # a distinct image, derived from the dark render
    assert rendered.provenance.has_light_variant is True
    assert rendered.provenance.light_mode == "retheme"
    # The edit seam was handed the dark render to re-theme, under a light-palette instruction.
    assert client.edit_kwargs, "images.edit was never called for the light re-theme"
    assert "light" in str(client.edit_kwargs.get("prompt", "")).lower()
