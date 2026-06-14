"""VideoPipeline tests: the real orchestration (PLAN → Gate A → Gate B → ASSEMBLE) wired
from real planner/gates with stubbed leaf seams, plus the contract-hash cache that skips the whole
render half on an unchanged contract, and the chaptered (overview) path that concatenates every
chapter's scenes into one MP4. Fakes stand in only for I/O leaves (model, renderer, vision, frames,
assembler, lesson source)."""

import json
from pathlib import Path

import pytest
from _stubs import FakeLessonProvider, StubInvokeModel, manifest_for
from lunaris_runtime.schema import VideoJob, VideoKind, VideoProvenance
from lunaris_runtime.video_build import target_seconds_for
from lunaris_video.assembly import build_webvtt
from lunaris_video.errors import FactualGateError
from lunaris_video.gates import FactualGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.models import RenderedScene, RenderedVideo, RenderResult
from lunaris_video.pipeline import ContractHashCache, VideoPipeline
from lunaris_video.pipeline.video_pipeline import SynthesizerProvider, _target_seconds
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import (
    ChapteredSceneContracts,
    QaVerdict,
    SceneContract,
    SceneTiming,
    SyncVerdict,
    TimingManifest,
    VideoContract,
)
from lunaris_video.voice import StubSpeechSynthesizer

_SCENE_SOURCE = (
    "from manim import *\n"
    "from style_tokens import *\n\n\n"
    "class S1Problem(Scene):\n"
    "    def construct(self):\n"
    "        pass\n"
)


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


class _SpyRenderer:
    """Writes a fake per-scene MP4 and counts renders — the cache assertion's instrument."""

    def __init__(self) -> None:
        self.renders = 0

    async def render(self, scene_file: Path, scene_class_name: str) -> "RenderResult":
        self.renders += 1
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake-mp4")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


class _CleanVision:
    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict:
        return QaVerdict(passed=True)


class _FakeFrames:
    async def extract(self, mp4_path: Path) -> list[bytes]:
        return [b"f30", b"f60", b"f90"]


class _SpyAssembler:
    def __init__(self) -> None:
        self.calls = 0
        self.received_manifest: TimingManifest | None = None
        self.received_contract: VideoContract | None = None
        self.received_audio_dir: Path | None = None

    async def assemble(
        self,
        scenes: list[RenderedScene],
        contract: VideoContract,
        *,
        manifest: TimingManifest,
        workdir: Path,
        audio_dir: Path | None = None,
    ) -> RenderedVideo:
        self.calls += 1
        self.received_manifest = manifest
        self.received_contract = contract
        self.received_audio_dir = audio_dir
        # Mirror the real assembler: captions ride only on a voiced (audio_dir-backed) render.
        captions = build_webvtt(contract, manifest).encode() if audio_dir is not None else None
        return RenderedVideo(
            mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
            poster=b"\xff\xd8\xff" + b"x" * 600,
            contracts_json=contract.model_dump_json().encode(),
            timing_json=manifest.model_dump_json().encode(),
            captions=captions,
        )


def _draft_json(make_lesson_contract) -> str:
    contract = make_lesson_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy")
    draft = {k: contract[k] for k in keys}
    # One scene, so the spy renderer count is unambiguous.
    draft["scenes"] = [contract["scenes"][0]]
    return json.dumps(draft)


class _CodegenStub:
    """A codegen seam that always returns valid scene source (Gate A/B never need to repair);
    records the per-scene timing it was handed (the audio-drives-video inversion's instrument)."""

    def __init__(self) -> None:
        self.generate_timings: list[SceneTiming] = []

    async def generate(self, scene: SceneContract, *, topic: str, timing: SceneTiming) -> str:
        self.generate_timings.append(timing)
        return _SCENE_SOURCE

    async def repair(
        self, scene: SceneContract, *, source: str, error_tail: str, timing: SceneTiming
    ) -> str:
        return _SCENE_SOURCE

    async def repair_visual(
        self, scene: SceneContract, *, source: str, defects, timing: SceneTiming
    ) -> str:
        return _SCENE_SOURCE


class _PassingSyncVision:
    """Gate D's vision double — every beat's frame matches its narration."""

    async def inspect(self, frame: bytes, *, narration: str, beat_id: str) -> SyncVerdict:
        return SyncVerdict(matches=True)


class _DummyFrameExtractor:
    """An ``ISyncFrameExtractor`` double for the hermetic voiced path (no real mp4 to probe)."""

    async def extract_at(self, mp4_path: Path, at_seconds: float) -> bytes:
        return b"frame"


def _passing_sync_gate() -> SyncGate:
    return SyncGate(vision=_PassingSyncVision(), frames=_DummyFrameExtractor())


def _voiced_job(job_id: str = "job-voiced") -> VideoJob:
    return VideoJob(
        id=job_id,
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
        config={"voice": True},
    )


def _pipeline(
    invoke: StubInvokeModel,
    renderer: _SpyRenderer,
    assembler: _SpyAssembler,
    cache: ContractHashCache,
    workspace: Path,
    codegen: _CodegenStub | None = None,
    synthesizer_provider: SynthesizerProvider = lambda: None,
    sync_gate: SyncGate | None = None,
    chaptered: bool = False,
) -> VideoPipeline:
    codegen = codegen or _CodegenStub()
    return VideoPipeline(
        source_provider=FakeLessonProvider(),
        planner=ScenePlanner(invoke=invoke),
        factual_gate=FactualGate(),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=_CleanVision(), codegen=codegen, renderer=renderer, frames=_FakeFrames()
        ),
        assembler=assembler,
        cache=cache,
        workspace_root=workspace,
        model_id="claude-test-model",
        chaptered=chaptered,
        synthesizer_provider=synthesizer_provider,
        sync_gate=sync_gate,
    )


async def test_produce_runs_the_pipeline_and_returns_the_assembled_video(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act
    video = await pipeline.produce(_job())

    # Assert — the real flow ran end to end: a scene rendered, the assembler bundled it, and the
    # returned artifact carries the planned contract (the planner sets the topic).
    assert renderer.renders == 1
    assert assembler.calls == 1
    assert video.mp4[4:8] == b"ftyp"
    assert b"How merge sort works" in video.contracts_json


async def test_produce_stamps_grounding_provenance_at_the_source(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — the planner grounds scene 1 on claim c1 (FakeLessonProvider's packet); the
    # provenance must record that claim id, the job, the contract hash, the model and a timestamp.
    contract = make_lesson_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy")
    draft: dict[str, object] = {k: contract[k] for k in keys}
    scene = contract["scenes"][0]
    scene["sources"] = ["c1"]
    draft["scenes"] = [scene]
    invoke = StubInvokeModel([json.dumps(draft)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act
    video = await pipeline.produce(_job())

    # Assert — provenance rides on the artifact, populated (not just an MP4 exists).
    provenance = VideoProvenance.model_validate_json(video.provenance_json)
    assert provenance.job_id == "job-1"
    assert provenance.input_hash == "hash-1"
    assert provenance.model == "claude-test-model"
    assert provenance.claim_ids == ["c1"]
    assert provenance.contract_hash  # the regeneration key, populated
    assert provenance.generated_at  # an ISO-8601 instant, stamped at the source


async def test_a_cache_hit_restamps_provenance_for_the_requesting_job(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — two different jobs produce the SAME contract (cache hit on the second). Provenance
    # must name the SECOND job, not the one that first rendered the contract.
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)
    job_two = VideoJob(
        id="job-2",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-2",
    )

    # Act — first job renders; second hits the cache.
    await pipeline.produce(_job())
    second = await pipeline.produce(job_two)

    # Assert — the cached render is reused, but provenance is the second job's own.
    assert renderer.renders == 1
    provenance = VideoProvenance.model_validate_json(second.provenance_json)
    assert provenance.job_id == "job-2"
    assert provenance.input_hash == "hash-2"


async def test_a_smuggled_figure_fails_gate_c_before_any_render(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — the planner emits a framing-only scene (cites no claim) that nonetheless narrates
    # "47% faster": a framing-only scene may assert no figure, so this is smuggled.
    contract = make_lesson_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy")
    draft: dict[str, object] = {k: contract[k] for k in keys}
    scene = contract["scenes"][0]
    scene["narration"] = "Sorting is 47% faster everywhere you look."
    draft["scenes"] = [scene]
    invoke = StubInvokeModel([json.dumps(draft)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act / Assert — Gate C runs on the contract right after PLAN, so the job fails before the
    # renderer is ever invoked (no compute wasted on ungrounded content).
    with pytest.raises(FactualGateError):
        await pipeline.produce(_job())
    assert renderer.renders == 0


async def test_an_unchanged_contract_hits_the_cache_and_skips_rendering(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — the SAME planner output both runs (the stub repeats its reply) → same hash.
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act — produce twice.
    first = await pipeline.produce(_job())
    second = await pipeline.produce(_job())

    # Assert — second produce skipped Stage 2+: no extra render, no extra assemble, and the cached
    # render bytes are reused (only provenance is restamped per produce, so the wrapper differs).
    assert renderer.renders == 1
    assert assembler.calls == 1
    assert second.mp4 == first.mp4
    assert second.contracts_json == first.contracts_json


async def test_the_timing_manifest_drives_codegen_then_is_persisted_unchanged(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — audio-drives-video: ONE manifest is resolved before the render, fed to the codegen,
    # and persisted as timing.json, so the code the model wrote and the player's manifest agree.
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    codegen = _CodegenStub()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path, codegen=codegen)

    # Act
    await pipeline.produce(_job())

    # Assert — the persisted manifest is the estimate of the planned contract (computed once, before
    # the render), and every scene's slice of THAT manifest drove the codegen (not render-then-fit).
    manifest = assembler.received_manifest
    assert manifest is not None
    assert manifest == manifest_for(assembler.received_contract)
    per_scene_timings = [manifest[scene_id] for scene_id in manifest.scene_ids()]
    assert codegen.generate_timings == per_scene_timings


async def test_one_contract_renders_silent_and_narrated_with_no_replan(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — the SAME lesson, run silent then narrated. The planner reply repeats (the stub),
    # so both produces plan the identical contract: the voice toggle must never re-plan.
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, cache = _SpyRenderer(), ContractHashCache()
    silent_assembler, narrated_assembler = _SpyAssembler(), _SpyAssembler()
    silent_pipeline = _pipeline(invoke, renderer, silent_assembler, cache, tmp_path)
    narrated_pipeline = _pipeline(
        invoke,
        renderer,
        narrated_assembler,
        cache,
        tmp_path,
        synthesizer_provider=lambda: StubSpeechSynthesizer(),
        sync_gate=_passing_sync_gate(),
    )

    # Act — one contract, two modes.
    silent = await silent_pipeline.produce(_job())
    narrated = await narrated_pipeline.produce(_voiced_job())

    # Assert — IDENTICAL contract (no re-plan); only the manifest/audio/captions differ.
    assert silent.contracts_json == narrated.contracts_json
    # No re-plan, mechanistically: the planner ran exactly once per produce (not extra). And the two
    # modes cache under DISTINCT keys, so each rendered from a cold start (no cross-mode cache hit).
    assert len(invoke.prompts) == 2
    assert renderer.renders == 2
    assert silent_assembler.received_audio_dir is None
    assert narrated_assembler.received_audio_dir is not None
    assert silent.captions is None
    assert narrated.captions is not None
    # Silent manifest = WPM estimate; narrated = measured TTS (a different, audio-driven timeline).
    assert silent_assembler.received_manifest is not None
    assert narrated_assembler.received_manifest is not None
    assert silent_assembler.received_manifest.is_voiced is False
    assert narrated_assembler.received_manifest.is_voiced is True
    assert silent_assembler.received_manifest != narrated_assembler.received_manifest


async def test_voice_on_without_a_key_degrades_to_silent(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — voice ON (the V6 default), but the default provider has no synthesizer (no validated
    # ElevenLabs key). This is the common keyed-user state: an Anthropic key but no optional BYOK
    # ElevenLabs key. It must render SILENT voice-ready (§0), never fail the whole video (AD-1).
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act — produces a real video, silent.
    video = await pipeline.produce(_voiced_job())

    # Assert — the scene rendered and assembled silent (the WPM-estimate manifest), no captions.
    assert renderer.renders == 1
    assert assembler.calls == 1
    assert assembler.received_audio_dir is None  # silent: no muxed narration
    assert assembler.received_manifest is not None
    assert assembler.received_manifest.is_voiced is False  # WPM estimate, not measured TTS
    assert video.captions is None


# ── V5: the chaptered (overview) path + configurable lengths ────────────────────────────


def _chaptered_draft_json(make_chaptered_contract) -> str:
    contract = make_chaptered_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy", "chapters")
    return json.dumps({k: contract[k] for k in keys})


def _overview_job() -> VideoJob:
    return VideoJob(
        id="job-overview",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id=None,  # course-level: no lesson
        kind=VideoKind.OVERVIEW,
        input_hash="hash-ovr",
    )


async def test_chaptered_overview_concatenates_every_chapter_into_one_mp4(
    make_chaptered_contract, tmp_path: Path
) -> None:
    # Arrange — the chaptered fixture is 2 chapters x 2 scenes; the pipeline is in chaptered mode
    # (the overview kind), so PLAN takes the chaptered branch.
    invoke = StubInvokeModel([_chaptered_draft_json(make_chaptered_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path, chaptered=True)

    # Act
    rendered = await pipeline.produce(_overview_job())

    # Assert — every chapter's scenes render (4 = 2x2), then a SINGLE assemble call concatenates
    # them into ONE continuous MP4 (plan §0: a chaptered contract → one video).
    assert renderer.renders == 4
    assert assembler.calls == 1
    assert isinstance(assembler.received_contract, ChapteredSceneContracts)
    assert len(assembler.received_contract.chapters) == 2
    assert len(assembler.received_contract.scenes) == 4  # chapters flattened in render order
    assert rendered.mp4  # one artifact


def test_target_seconds_falls_back_to_the_kind_default_when_unconfigured() -> None:
    # A job with no configured length designs to its kind's product default (V5-T1).
    job = VideoJob(id="j", user_id="u", course_id="c1", kind=VideoKind.OVERVIEW, input_hash="h")
    assert _target_seconds(job) == target_seconds_for(VideoKind.OVERVIEW)


def test_target_seconds_uses_the_configured_length_when_present() -> None:
    # A snapshotted custom length (a future per-user config, V6) is respected over the default.
    job = VideoJob(
        id="j",
        user_id="u",
        course_id="c1",
        kind=VideoKind.OVERVIEW,
        input_hash="h",
        config={"target_seconds": 240},
    )
    assert _target_seconds(job) == 240
