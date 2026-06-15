"""Gate D tests: the sync gate is a per-scene REPAIR LOOP (not fail-clean). For each spoken beat it
samples the frame at the beat's midpoint on THIS scene's timeline and asks the vision seam whether
it shows what the narration says; on a miss it drives a targeted ``repair_sync`` codegen turn (move
the reveal to the start of the window), re-renders ONLY that scene, and re-checks — to the cap. A
scene that syncs returns ``(render, None)``; a beat whose desync survives the budget is shipped
best-effort — the gate returns the closest render and the unsynced beat id, never silencing the
video. The frame's visual is identical pre/post mux, so the check runs on the per-scene render.

Fakes stand in for vision, frame extraction, codegen and the renderer; the loop under test is real.
"""

from collections.abc import Callable
from pathlib import Path

from lunaris_video.gates import SyncGate
from lunaris_video.gates.sync_gate import _REPAIR_CAP_PER_SCENE
from lunaris_video.models import RenderedScene, RenderResult
from lunaris_video.schemas import Beat, BeatTiming, SceneContract, SceneTiming, SyncVerdict

_DESYNC_REASON = "the narration names the loss, but it is not on screen yet"

# The fixture scene (conftest) has spoken b1, spoken b2 and silent b3. Its measured timing: b1 fills
# 0-2s (midpoint 1.0), b2 fills 2-5s (midpoint 3.5), silent b3 fills 5-6.5s (never inspected).
_LOCAL_MIDPOINTS = {"b1": 1.0, "b2": 3.5}


def _timing() -> SceneTiming:
    return SceneTiming(
        beats=[
            BeatTiming(id="b1", audio_s=2.0, anim_s=2.0, audio="b1.mp3", estimated=False),
            BeatTiming(id="b2", audio_s=3.0, anim_s=3.0, audio="b2.mp3", estimated=False),
            BeatTiming(id="b3", audio_s=0.0, anim_s=1.5, audio=None, estimated=False),
        ],
        total_s=6.5,
    )


class _FakeSyncVision:
    """Desyncs ``fail_beat`` for its first ``fail_rounds`` inspections, then matches it. Records the
    beat ids it inspects in order, so a test can prove which beats were sampled and how often."""

    def __init__(self, *, fail_beat: str | None = None, fail_rounds: int = 0) -> None:
        self._fail_beat = fail_beat
        self._fails_left = fail_rounds
        self.inspected: list[str] = []

    async def inspect(self, frame: bytes, *, narration: str, beat_id: str) -> SyncVerdict:
        self.inspected.append(beat_id)
        if beat_id == self._fail_beat and self._fails_left > 0:
            self._fails_left -= 1
            return SyncVerdict(matches=False, reason=_DESYNC_REASON)
        return SyncVerdict(matches=True)


class _RecordingExtractor:
    """An ``ISyncFrameExtractor`` double: records the timestamps the gate samples; returns bytes."""

    def __init__(self) -> None:
        self.timestamps: list[float] = []

    async def extract_at(self, mp4_path: Path, at_seconds: float) -> bytes:
        self.timestamps.append(at_seconds)
        return b"frame-bytes"


class _RepairSyncCodegen:
    """Fakes only the sync-repair arm of ISceneCodeGenerator; records (beat_id, reason) per call."""

    def __init__(self) -> None:
        self.repairs: list[tuple[str, str]] = []

    async def repair_sync(
        self, scene: SceneContract, *, source: str, beat_id: str, reason: str, timing: SceneTiming
    ) -> str:
        self.repairs.append((beat_id, reason))
        return f"{source}# sync repair {len(self.repairs)}\n"


class _FakeRenderer:
    def __init__(self) -> None:
        self.renders = 0

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        self.renders += 1
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


class _RendererFailingAfter:
    """Succeeds for the first ``ok`` renders, then fails — models a sync repair that breaks the
    render (the gate must degrade to the best prior render, not loop forever)."""

    def __init__(self, ok: int) -> None:
        self.renders = 0
        self._ok = ok

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        self.renders += 1
        if self.renders > self._ok:
            return RenderResult(succeeded=False, mp4_path=None, error_tail="manim: blew up")
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


def _rendered(tmp_path: Path) -> RenderedScene:
    mp4 = tmp_path / "S1Problem.mp4"
    mp4.write_bytes(b"fake")
    return RenderedScene(scene_id="S1_problem", mp4_path=mp4, source="# original\n")


def _gate(vision: object, codegen: object, renderer: object) -> SyncGate:
    # The embedded extractor's timestamps are not inspected on these paths — the vision/codegen/
    # renderer spies are the instruments. The sampling geometry has its own dedicated test.
    return SyncGate(vision=vision, frames=_RecordingExtractor(), codegen=codegen, renderer=renderer)


async def test_a_synced_scene_passes_without_repair(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — every spoken beat's midpoint frame matches its narration.
    vision = _FakeSyncVision()
    frames = _RecordingExtractor()
    codegen, renderer = _RepairSyncCodegen(), _FakeRenderer()
    gate = SyncGate(vision=vision, frames=frames, codegen=codegen, renderer=renderer)

    # Act
    scene, unsynced = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_timing(), workdir=tmp_path
    )

    # Assert — passed untouched: no repair, no re-render, the original artifact returned, no
    # unsynced beat. Only the two SPOKEN beats were inspected, each sampled at its window midpoint
    # on THIS scene's timeline (the silent b3 advances the clock but is never sampled).
    assert unsynced is None
    assert scene.source == "# original\n"
    assert codegen.repairs == []
    assert renderer.renders == 0
    assert vision.inspected == ["b1", "b2"]
    assert [round(t, 4) for t in frames.timestamps] == [
        _LOCAL_MIDPOINTS["b1"],
        _LOCAL_MIDPOINTS["b2"],
    ]


async def test_a_desynced_beat_is_repaired_re_rendered_and_re_checked(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — b1 desyncs on the first look, then lines up after one targeted sync repair.
    vision = _FakeSyncVision(fail_beat="b1", fail_rounds=1)
    codegen, renderer = _RepairSyncCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    scene, unsynced = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_timing(), workdir=tmp_path
    )

    # Assert — the desync drove ONE targeted sync repair (carrying the offending beat + the vision
    # model's reason), a re-render of just this scene, and a re-check that passed; the repaired
    # source ships with no unsynced beat.
    assert unsynced is None
    assert codegen.repairs == [("b1", _DESYNC_REASON)]
    assert renderer.renders == 1
    assert scene.source.endswith("# sync repair 1\n")


async def test_a_later_beat_desync_is_repaired_after_an_earlier_beat_passes(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — b1 syncs but b2 (a LATER beat) desyncs once, then lines up. This exercises the
    # non-first-beat path: the cursor must advance past b1 before sampling b2's midpoint (the
    # coverage the old multi-scene check pinned with a later-ordinal failure).
    vision = _FakeSyncVision(fail_beat="b2", fail_rounds=1)
    codegen, renderer = _RepairSyncCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    scene, unsynced = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_timing(), workdir=tmp_path
    )

    # Assert — the repair named b2 (not b1), and each inspection walked b1 (passing) before b2: the
    # first round desyncs at b2, the post-repair round re-walks b1 then b2 and converges (synced).
    assert unsynced is None
    assert codegen.repairs == [("b2", _DESYNC_REASON)]
    assert renderer.renders == 1
    assert vision.inspected == ["b1", "b2", "b1", "b2"]
    assert scene.source.endswith("# sync repair 1\n")


async def test_a_persistent_desync_ships_the_best_render_and_records_the_beat(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — b1 never lines up, no matter how many repairs.
    vision = _FakeSyncVision(fail_beat="b1", fail_rounds=99)
    codegen, renderer = _RepairSyncCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act — bounded at the per-scene cap (3 repairs / 4 inspections), then DEGRADES (never raises):
    # ships the closest render and records the unsynced beat so the video stays voiced.
    scene, unsynced = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_timing(), workdir=tmp_path
    )

    # Assert — the offending beat is reported (not raised), the LAST repair render ships, and the
    # loop ran its full budget (cap repairs / cap+1 inspections).
    assert unsynced == "b1"
    assert scene.source.endswith(
        f"# sync repair {_REPAIR_CAP_PER_SCENE}\n"
    )  # the last render ships
    assert len(vision.inspected) == _REPAIR_CAP_PER_SCENE + 1  # 1 initial + cap repairs
    assert len(codegen.repairs) == _REPAIR_CAP_PER_SCENE
    assert renderer.renders == _REPAIR_CAP_PER_SCENE


async def test_a_sync_repair_that_breaks_the_render_ships_the_best_prior_render(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — b1 desyncs and the first sync repair breaks the render entirely.
    vision = _FakeSyncVision(fail_beat="b1", fail_rounds=99)
    codegen, renderer = _RepairSyncCodegen(), _RendererFailingAfter(ok=0)
    gate = _gate(vision, codegen, renderer)

    # Act — a repair that breaks the render stops the loop (no render storm) and degrades: ships the
    # best prior renderable scene (the original) and records the unsynced beat.
    scene, unsynced = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_timing(), workdir=tmp_path
    )

    # Assert — the repair WAS attempted (carrying the vision reason) before the render broke, then
    # one (failed) repair-render, then degrade to the original renderable scene.
    assert unsynced == "b1"
    assert codegen.repairs == [("b1", _DESYNC_REASON)]
    assert scene.source == "# original\n"
    assert renderer.renders == 1


async def test_a_silent_middle_beat_advances_the_cursor_without_being_sampled(
    tmp_path: Path,
) -> None:
    # Arrange — a scene with a SILENT beat BETWEEN two spoken beats. This proves the cursor advances
    # through silent beats: if it didn't, the SECOND spoken beat's midpoint would be computed too
    # early (the bug the old global-cursor code could mask).
    scene = SceneContract(
        id="S1_problem",
        archetype="process/flow",
        narration="First this. Then that.",
        objects=["a", "b"],
        beats=[
            Beat(id="b1", action="reveal a", narration="First this."),
            Beat(id="b2", action="hold", narration="", min_visual_s=2.0),
            Beat(id="b3", action="reveal b", narration="Then that."),
        ],
        sources=["framing only - no empirical claims"],
        duration_s=10,
    )
    timing = SceneTiming(
        beats=[
            BeatTiming(id="b1", audio_s=2.0, anim_s=2.0, audio="b1.mp3", estimated=False),
            BeatTiming(id="b2", audio_s=0.0, anim_s=2.0, audio=None, estimated=False),
            BeatTiming(id="b3", audio_s=3.0, anim_s=3.0, audio="b3.mp3", estimated=False),
        ],
        total_s=7.0,
    )
    vision, frames = _FakeSyncVision(), _RecordingExtractor()
    gate = SyncGate(
        vision=vision, frames=frames, codegen=_RepairSyncCodegen(), renderer=_FakeRenderer()
    )

    # Act
    await gate.inspect_scene(scene, rendered=_rendered(tmp_path), timing=timing, workdir=tmp_path)

    # Assert — only the two spoken beats are sampled; b3's midpoint (5.5 = 2 + 2 + 3/2) INCLUDES the
    # silent b2's window. A cursor that skipped silent beats would put b3 at 3.5 — caught here.
    assert vision.inspected == ["b1", "b3"]
    assert [round(t, 4) for t in frames.timestamps] == [1.0, 5.5]
