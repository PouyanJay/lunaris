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
from _general_fields import FIELDS_JSON, FIELDS_JSON_REVISED, is_fields_ask
from lunaris_covers.art_direction.cover_art_director import CoverArtDirector
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.pipeline.cover_pipeline import CoverPipeline
from lunaris_covers.rendering.openai_image_renderer import OpenAiImageRenderer
from lunaris_covers.schemas.cover_qa_verdict import CoverQaDefect, CoverQaVerdict
from lunaris_covers.sourcing.course_store_cover_source_provider import (
    CourseStoreCoverSourceProvider,
)
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
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
    """A fake ``TextInvoke``: canned prose for the editorial ask, valid fields JSON for the GENERAL
    structured ask (identified by its JSON contract)."""

    def __init__(
        self, reply: str = "A lone amber lighthouse over a near-black sea, vast sky."
    ) -> None:
        self.reply = reply
        self.prompt: str | None = None

    async def __call__(self, prompt: str) -> str:
        self.prompt = prompt
        if is_fields_ask(prompt):
            return FIELDS_JSON
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
        # The light-twin capability is default-OFF; these tests exercise it deliberately.
        light_variant=True,
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

    async def inspect(self, image: bytes, brief: object, *, light: bool = False) -> CoverQaVerdict:
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
        light_variant=True,
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
    assert inspector.calls == 2  # one dark QA (passed) + one light-variant QA (passed)


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
    # The edit seam was handed the dark render to re-theme, under a light-palette instruction —
    # and the JOB's preset (nocturne here) picked the palette: amber, never the general azure.
    assert client.edit_kwargs, "images.edit was never called for the light re-theme"
    edit_prompt = str(client.edit_kwargs.get("prompt", "")).lower()
    assert "light" in edit_prompt
    assert "amber" in edit_prompt and "azure" not in edit_prompt


@pytest.mark.asyncio
async def test_general_job_sends_the_full_operator_template_to_the_image_model() -> None:
    # General-preset template fidelity, pinned at the INTEGRATION seam: the prompt GPT Image 2
    # receives must be the operator's full structured template (Claude fills only the fields) —
    # not a prose paraphrase. The compression to 2-4 sentences is exactly the production bug that
    # made general covers look nothing like the references.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _FakeImagesClient()

    rendered = await _pipeline(store, _StubArtDirectorInvoke(), client).produce(
        _job(CoverStylePreset.GENERAL), on_stage=_noop_stage
    )

    sent = str(client.kwargs["prompt"])
    assert "Create a premium, enterprise-grade 16:9 educational course cover" in sent
    # The TYPOGRAPHY Claude wrote is typeset into the cover — the composed-cover contract.
    assert "PROFESSIONAL EDUCATION COURSE" in sent
    assert 'Typeset the line "HTTPS" in rich amber' in sent
    assert "FOUNDATIONAL / PRACTICAL / ESSENTIAL" in sent
    assert "correctly spelled and legible" in sent
    # Amber as the dominant grade + the whole-subject anchor (pathology-plate / anchor fixes).
    assert "Amber is the DOMINANT GRADE" in sent
    assert "WHOLE, immediately recognizable subject as the anchor" in sent
    assert "near-black, charcoal, and deep graphite" in sent  # the dark amber theme, verbatim
    assert "- Hero: a refined 3D hero mechanism" in sent  # Claude's artwork field, in its slot
    # The image model is asked on the 16:9 canvas the composed cover is designed for.
    assert client.kwargs["size"] == "2048x1152"
    # Provenance records the full prompt actually sent, not a summary.
    assert rendered.provenance.prompt == sent


@pytest.mark.asyncio
async def test_light_retheme_uses_the_jobs_preset_palette() -> None:
    # The wiring this exists to pin: the pipeline must thread the JOB's style preset into the light
    # re-theme instruction. A GENERAL job re-themes to the azure light palette — a hardcoded preset
    # anywhere in the chain would ship amber here and fail this test.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _FakeImagesClient()

    await _pipeline(store, _StubArtDirectorInvoke(), client).produce(
        _job(CoverStylePreset.GENERAL), on_stage=_noop_stage
    )

    edit_prompt = str(client.edit_kwargs.get("prompt", "")).lower()
    assert "azure" in edit_prompt and "amber" not in edit_prompt


class _LightAwareInspector:
    """A vision-QA double that verdicts dark and light variants independently.

    The dark cover always passes; the light QA fails its first ``light_fail_first`` inspections then
    passes — so a test can drive the re-theme→native-light→dark-only ladder deterministically. Every
    call records which variant it judged.
    """

    def __init__(self, *, light_fail_first: int = 0) -> None:
        self._light_fail_first = light_fail_first
        self.model = "claude-opus-4-8"
        self.dark_calls = 0
        self.light_calls = 0
        self.variants: list[str] = []

    async def inspect(self, image: bytes, brief: object, *, light: bool = False) -> CoverQaVerdict:
        self.variants.append("light" if light else "dark")
        if not light:
            self.dark_calls += 1
            return CoverQaVerdict(passed=True)
        self.light_calls += 1
        if self.light_calls <= self._light_fail_first:
            return CoverQaVerdict(passed=False, defects=[CoverQaDefect(issue="washed out")])
        return CoverQaVerdict(passed=True)


def _light_pipeline(
    store: _FakeCourseStore, client: _CountingImagesClient, inspector: _LightAwareInspector
) -> CoverPipeline:
    return CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=_RecordingArtInvoke(), model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=lambda: client),
        qa_model="claude-opus-4-8",
        inspector=inspector,
        light_variant=True,
    )


@pytest.mark.asyncio
async def test_light_variant_that_passes_qa_is_kept_as_a_retheme() -> None:
    # The re-theme (same composition) passes the light QA → it is kept, recorded as "retheme".
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _CountingImagesClient()
    inspector = _LightAwareInspector(light_fail_first=0)

    rendered = await _light_pipeline(store, client, inspector).produce(_job(), on_stage=_noop_stage)

    assert rendered.provenance.has_light_variant is True
    assert rendered.provenance.light_mode == "retheme"
    assert rendered.image_light is not None and rendered.image_light != rendered.image
    assert inspector.light_calls == 1  # the re-theme was QA'd once and accepted
    assert client.edits == 1 and client.renders == 1  # no native render needed


@pytest.mark.asyncio
async def test_a_washed_out_retheme_falls_back_to_a_native_light_cover() -> None:
    # The re-theme fails the light QA (reads washed) → a NATIVE light cover is art-directed + QA'd.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _CountingImagesClient()
    inspector = _LightAwareInspector(light_fail_first=1)  # retheme fails, native passes

    rendered = await _light_pipeline(store, client, inspector).produce(_job(), on_stage=_noop_stage)

    assert rendered.provenance.has_light_variant is True
    assert rendered.provenance.light_mode == "native"
    assert client.edits == 1  # the re-theme was attempted
    assert client.renders == 2  # the dark render + the native light render
    assert inspector.light_calls == 2  # QA'd the failed re-theme, then the passing native
    # The kept light image is the NATIVE render (a generate call, renders=2 → _PNG + byte 2), not
    # the re-theme edit output (which would carry the b"L" marker).
    assert rendered.image_light == _PNG + bytes([2])


@pytest.mark.asyncio
async def test_light_variant_exhausted_ships_a_dark_only_cover() -> None:
    # Neither the re-theme nor the native light cover can pass QA → ship dark-only, never fail the
    # job. The dark cover already passed; the reader shows it in both themes (like an old cover).
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _CountingImagesClient()
    inspector = _LightAwareInspector(light_fail_first=99)  # light never passes

    rendered = await _light_pipeline(store, client, inspector).produce(_job(), on_stage=_noop_stage)

    assert rendered.image is not None  # the dark cover still ships
    assert rendered.image_light is None
    assert rendered.provenance.has_light_variant is False
    assert rendered.provenance.light_mode is None
    assert inspector.light_calls == 2  # bounded: one re-theme QA + one native QA, then give up
    assert client.edits == 1 and client.renders == 2  # exactly one re-theme + one native attempt


# ---- dual-theme: the light variant NEVER fails the whole job (AD2) ---------------------------


class _ConfigurableRenderer:
    """A fake ``IImageRenderer`` whose dark render works but whose LIGHT calls can be made to raise.

    Proves the light path degrades to a dark-only cover on a provider failure rather than letting
    the error propagate out of ``produce`` and fail a job whose dark cover already passed QA (AD2).
    ``render_raises_on_call`` targets the Nth ``render`` (call 1 = the dark render, call 2 = the
    native light render)."""

    def __init__(
        self, *, retheme_raises: bool = False, render_raises_on_call: int | None = None
    ) -> None:
        self.model = "gpt-image-2"
        self.render_calls = 0
        self._retheme_raises = retheme_raises
        self._render_raises_on_call = render_raises_on_call

    async def render(self, prompt: str) -> bytes:
        self.render_calls += 1
        if self.render_calls == self._render_raises_on_call:
            raise CoverPipelineError("render failed", user_detail="provider down")
        return _PNG + bytes([self.render_calls])

    async def retheme(self, image: bytes, *, instruction: str) -> bytes:
        if self._retheme_raises:
            raise CoverPipelineError("re-theme failed", user_detail="provider down")
        return _PNG + b"L"


class _LightQaRaisesInspector:
    """Dark QA passes; every LIGHT QA call raises (parse-exhaustion / provider error) instead of
    returning a verdict — the gap the review caught: an unwrapped QA exception must not fail it."""

    def __init__(self) -> None:
        self.model = "claude-opus-4-8"
        self.dark_calls = 0
        self.light_calls = 0

    async def inspect(self, image: bytes, brief: object, *, light: bool = False) -> CoverQaVerdict:
        if not light:
            self.dark_calls += 1
            return CoverQaVerdict(passed=True)
        self.light_calls += 1
        raise ValueError("light QA parse exhausted")


def _pipeline_with(store: _FakeCourseStore, renderer: object, inspector: object) -> CoverPipeline:
    return CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=_RecordingArtInvoke(), model="claude-opus-4-8"),
        renderer=renderer,  # type: ignore[arg-type]
        qa_model="claude-opus-4-8",
        inspector=inspector,  # type: ignore[arg-type]
        light_variant=True,
    )


def _assert_dark_only(rendered: object) -> None:
    assert rendered.image is not None  # type: ignore[attr-defined] — the dark cover still ships
    assert rendered.image_light is None  # type: ignore[attr-defined]
    assert rendered.provenance.has_light_variant is False  # type: ignore[attr-defined]
    assert rendered.provenance.light_mode is None  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_retheme_provider_error_degrades_to_a_dark_only_cover() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    inspector = _LightAwareInspector()  # dark passes; light QA never reached

    rendered = await _pipeline_with(
        store, _ConfigurableRenderer(retheme_raises=True), inspector
    ).produce(_job(), on_stage=_noop_stage)

    _assert_dark_only(rendered)
    assert inspector.light_calls == 0  # the re-theme raised before any light QA


@pytest.mark.asyncio
async def test_a_native_render_error_degrades_to_a_dark_only_cover() -> None:
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    # The re-theme QA fails → native path; the native render (the 2nd render call) then raises.
    renderer = _ConfigurableRenderer(render_raises_on_call=2)
    inspector = _LightAwareInspector(light_fail_first=1)

    rendered = await _pipeline_with(store, renderer, inspector).produce(
        _job(), on_stage=_noop_stage
    )

    _assert_dark_only(rendered)
    assert renderer.render_calls == 2  # dark render + the native render that raised


@pytest.mark.asyncio
async def test_a_light_qa_exception_degrades_to_a_dark_only_cover() -> None:
    # The review's blocking gap: a light-QA exception (parse-exhaustion / provider error) must be
    # swallowed as a miss, not propagate out of produce() and fail the whole job.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    inspector = _LightQaRaisesInspector()

    rendered = await _pipeline_with(store, _ConfigurableRenderer(), inspector).produce(
        _job(), on_stage=_noop_stage
    )

    _assert_dark_only(rendered)
    assert inspector.dark_calls == 1  # the dark cover was still QA'd and shipped
    assert inspector.light_calls == 2  # both light QA attempts raised and were absorbed


# ---- GENERAL regenerate round + parse-repair exhaustion (review: the untested new paths) ----


class _GeneralSequenceInvoke:
    """A ``TextInvoke`` for GENERAL jobs: returns a different fields JSON per fields-ask, recording
    every prompt — so a test can prove the revision round carried the defects and produced NEW
    fields, not a re-roll of the first attempt's."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._replies[min(len(self.prompts), len(self._replies)) - 1]


@pytest.mark.asyncio
async def test_general_qa_rejection_revises_the_fields_and_reassembles_the_template() -> None:
    # The GENERAL regenerate round: QA rejects the first render → the art director is re-asked for
    # NEW fields with the defects folded in → the template is re-assembled with those new fields.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)
    client = _CountingImagesClient()
    invoke = _GeneralSequenceInvoke([FIELDS_JSON, FIELDS_JSON_REVISED])
    inspector = _ScriptedInspector(fail_first=1)  # reject round 1, pass round 2

    rendered = await CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=invoke, model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=lambda: client),
        qa_model="claude-opus-4-8",
        inspector=inspector,
    ).produce(_job(CoverStylePreset.GENERAL), on_stage=_noop_stage)

    assert rendered.provenance.qa_attempts == 2
    # Round 2's fields-ask carried the QA defect (and stayed a fields-ask, not a prose ask).
    assert len(invoke.prompts) == 2
    assert is_fields_ask(invoke.prompts[1])
    assert "defect round 1" in invoke.prompts[1]
    # The prior attempt's assembled template must NOT leak into the retry's fields-ask.
    assert "COLOR THEME:" not in invoke.prompts[1]
    # The winning prompt is the template re-assembled with the REVISED fields.
    assert "a calmer matte-ceramic hero mechanism" in rendered.provenance.prompt
    assert "Typography in the left third" in rendered.provenance.prompt


@pytest.mark.asyncio
async def test_general_fields_that_never_parse_fail_with_an_actionable_reason() -> None:
    # Parse-repair exhaustion (review): a GENERAL invoke that never yields valid fields JSON must
    # fail as a CoverPipelineError with an owner-safe, actionable user_detail — the worker then
    # settles the job FAILED with that reason (its CoverPipelineError contract) instead of leaking
    # a raw ValidationError class name. Bounded: exactly the repair budget, no runaway loop.
    store = _FakeCourseStore()
    store.seed(_course(), owner_id=_OWNER)

    class _GarbageInvoke:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, prompt: str) -> str:
            self.calls += 1
            return "not json at all"

    invoke = _GarbageInvoke()
    pipeline = CoverPipeline(
        source_provider=CourseStoreCoverSourceProvider(store),
        art_director=CoverArtDirector(invoke=invoke, model="claude-opus-4-8"),
        renderer=OpenAiImageRenderer(client_factory=_FakeImagesClient),
        qa_model="claude-opus-4-8",
    )
    with pytest.raises(CoverPipelineError) as caught:
        await pipeline.produce(_job(CoverStylePreset.GENERAL), on_stage=_noop_stage)

    assert caught.value.user_detail == "couldn't write the cover's descriptive fields"
    assert invoke.calls == DEFAULT_PARSE_REPAIR_ATTEMPTS  # bounded — the repair budget, no more
