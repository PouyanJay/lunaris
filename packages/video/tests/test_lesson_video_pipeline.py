"""LessonVideoPipeline tests: the real orchestration (PLAN → Gate A → Gate B → ASSEMBLE) wired
from real planner/gates with stubbed leaf seams, plus the contract-hash cache that skips the whole
render half on an unchanged contract. Fakes stand in only for I/O leaves (model, renderer, vision,
frames, assembler, lesson source)."""

import json
from pathlib import Path

import pytest
from _stubs import FakeLessonProvider, StubInvokeModel, manifest_for
from lunaris_runtime.schema import VideoJob, VideoKind, VideoProvenance
from lunaris_video.errors import FactualGateError
from lunaris_video.gates import FactualGate, RenderGate, VisualQaGate
from lunaris_video.models import RenderedScene, RenderedVideo, RenderResult
from lunaris_video.pipeline import ContractHashCache, LessonVideoPipeline
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import (
    QaVerdict,
    SceneContract,
    SceneTiming,
    TimingManifest,
    VideoContract,
)

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

    async def assemble(
        self,
        scenes: list[RenderedScene],
        contract: VideoContract,
        *,
        manifest: TimingManifest,
        workdir: Path,
    ) -> RenderedVideo:
        self.calls += 1
        self.received_manifest = manifest
        self.received_contract = contract
        return RenderedVideo(
            mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
            poster=b"\xff\xd8\xff" + b"x" * 600,
            contracts_json=contract.model_dump_json().encode(),
            timing_json=manifest.model_dump_json().encode(),
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


def _pipeline(
    invoke: StubInvokeModel,
    renderer: _SpyRenderer,
    assembler: _SpyAssembler,
    cache: ContractHashCache,
    workspace: Path,
    codegen: _CodegenStub | None = None,
) -> LessonVideoPipeline:
    codegen = codegen or _CodegenStub()
    return LessonVideoPipeline(
        lesson_provider=FakeLessonProvider(),
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
