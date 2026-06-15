import asyncio
from pathlib import Path

import structlog

from lunaris_video.errors import SceneRenderError, SyncGateError
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.protocols.scene_code_generator_protocol import ISceneCodeGenerator
from lunaris_video.protocols.scene_renderer_protocol import ISceneRenderer
from lunaris_video.protocols.sync_frame_extractor_protocol import ISyncFrameExtractor
from lunaris_video.protocols.sync_qa_protocol import ISyncQa
from lunaris_video.schemas import SceneContract, SceneTiming

_logger = structlog.get_logger(__name__)

# Mirrors Gate B's budget: an initial check plus up to N targeted sync repairs. Front-loading (the
# codegen rule) makes a first-pass miss rare; a few "move the reveal to the start" repairs catch the
# rest. Beyond that the pipeline ships the SILENT (sync-exempt) version — never a desync.
_REPAIR_CAP_PER_SCENE = 3
_INSPECTIONS = _REPAIR_CAP_PER_SCENE + 1


class SyncGate:
    """Gate D: every spoken beat's frame at its window midpoint must show what its narration says.

    Per scene (narrated only), this is a REPAIR LOOP — the same shape as Gate B, not the old
    fail-on-first-miss gate. It samples each spoken beat at its midpoint on THIS scene's timeline
    (``sum(anim_s of earlier beats) + anim_s/2``); on a miss it drives a targeted ``repair_sync``
    codegen turn (move the narrated reveal to the START of the beat window, hold the rest),
    re-renders ONLY this scene, and re-checks — up to the repair cap. A scene that syncs ships; a
    beat whose desync survives the budget (or whose repair breaks the render) raises
    ``SyncGateError``, which the pipeline recovers by delivering the silent version — never a
    narration/visual mismatch.

    The frame's VISUAL is identical before and after the audio mux, so the check runs on the
    per-scene render (before assembly): that is what makes the repair loop cheap — re-render one
    scene, never re-assemble the whole video. Silent beats advance the clock but are never inspected
    — there is nothing spoken to verify.
    """

    def __init__(
        self,
        *,
        vision: ISyncQa,
        frames: ISyncFrameExtractor,
        codegen: ISceneCodeGenerator,
        renderer: ISceneRenderer,
    ) -> None:
        self._vision = vision
        self._frames = frames
        self._codegen = codegen
        self._renderer = renderer

    async def inspect_scene(
        self, scene: SceneContract, *, rendered: RenderedScene, timing: SceneTiming, workdir: Path
    ) -> RenderedScene:
        current = rendered
        # The last desync seen (beat id + the vision reason), initialised before the loop so the
        # fail-clean raise after it is provably bound — mirrors Gate B's ``best_defects`` guard.
        last_miss: tuple[str, str] | None = None
        for inspection in range(_INSPECTIONS):
            miss = await self._first_desynced_beat(scene, current, timing)
            if miss is None:
                _logger.info("sync_gate.scene_passed", scene_id=scene.id, repairs=inspection)
                return current
            last_miss = miss
            if inspection == _INSPECTIONS - 1:
                break  # repair budget exhausted — fail clean (the pipeline delivers silent)
            try:
                current = await self._repair_and_rerender(
                    scene, current, beat_id=miss[0], reason=miss[1], timing=timing, workdir=workdir
                )
            except SceneRenderError:
                # A sync repair that breaks the render: stop and fail clean rather than loop.
                _logger.warning("sync_gate.repair_broke_render", scene_id=scene.id, beat_id=miss[0])
                break
        assert last_miss is not None  # the loop only exits here after a miss was recorded
        beat_id, reason = last_miss
        _logger.warning("sync_gate.scene_desynced", scene_id=scene.id, beat_id=beat_id)
        raise SyncGateError(beat_id, reason=reason)

    async def _first_desynced_beat(
        self, scene: SceneContract, rendered: RenderedScene, timing: SceneTiming
    ) -> tuple[str, str] | None:
        """The first spoken beat whose midpoint frame doesn't match its words (beat id + the vision
        reason), or ``None`` if every spoken beat syncs. The midpoint is on THIS scene's timeline —
        each per-scene MP4 starts at 0 — a silent beat advances the cursor but is never sampled."""
        timing_by_beat = {beat.id: beat for beat in timing.beats}
        cursor = 0.0
        for beat in scene.beats:
            window = timing_by_beat[beat.id]
            midpoint = cursor + window.anim_s / 2
            cursor += window.anim_s
            if window.audio is None or not beat.narration.strip():
                continue  # a silent beat: nothing is spoken at this instant to verify
            frame = await self._frames.extract_at(rendered.mp4_path, midpoint)
            verdict = await self._vision.inspect(frame, narration=beat.narration, beat_id=beat.id)
            if not verdict.matches:
                return beat.id, verdict.reason
        return None

    async def _repair_and_rerender(
        self,
        scene: SceneContract,
        current: RenderedScene,
        *,
        beat_id: str,
        reason: str,
        timing: SceneTiming,
        workdir: Path,
    ) -> RenderedScene:
        source = await self._codegen.repair_sync(
            scene, source=current.source, beat_id=beat_id, reason=reason, timing=timing
        )
        scene_file = workdir / f"{scene.id}.py"
        await asyncio.to_thread(scene_file.write_text, source, encoding="utf-8")
        result = await self._renderer.render(scene_file, scene.scene_class_name)
        if not result.succeeded or result.mp4_path is None:
            # A sync fix that breaks the render: surfaced to the loop, which stops and fails clean.
            raise SceneRenderError(scene.id, attempts=1, error_tail=result.error_tail)
        return RenderedScene(scene_id=scene.id, mp4_path=result.mp4_path, source=source)
