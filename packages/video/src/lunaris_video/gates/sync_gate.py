from pathlib import Path

import structlog

from lunaris_video.errors import SyncGateError
from lunaris_video.protocols.sync_frame_extractor_protocol import ISyncFrameExtractor
from lunaris_video.protocols.sync_qa_protocol import ISyncQa
from lunaris_video.schemas import TimingManifest, VideoContract

_logger = structlog.get_logger(__name__)


class SyncGate:
    """Gate D: each spoken beat's frame at its audio midpoint must show what its narration says.

    Runs on the muxed (narrated) video, narrated-only. For each spoken beat it extracts the frame at
    the beat's midpoint on the GLOBAL (concatenated) timeline — ``sum(anim_s of earlier beats) +
    anim_s/2`` — and asks the vision seam whether it matches the words. A mismatch raises
    ``SyncGateError`` (fail-clean, no auto-repair): sync is deterministic by construction, so a
    desync is a codegen bug or a re-plan case, which the V6 regenerate path owns (mirrors Gate C).
    Silent beats advance the clock but are never inspected — there is nothing spoken to verify.
    """

    def __init__(self, *, vision: ISyncQa, frames: ISyncFrameExtractor) -> None:
        self._vision = vision
        self._frames = frames

    async def check(
        self, video_path: Path, contract: VideoContract, manifest: TimingManifest
    ) -> None:
        cursor = 0.0
        for scene in contract.scenes:
            timing_by_beat = {beat.id: beat for beat in manifest[scene.id].beats}
            for beat in scene.beats:
                timing = timing_by_beat[beat.id]
                midpoint = cursor + timing.anim_s / 2
                # Advance the global clock now — a silent beat still occupies its window on the
                # concatenated timeline, so the next beat's midpoint must include it.
                cursor += timing.anim_s
                if timing.audio is None or not beat.narration.strip():
                    continue  # a silent beat: nothing is spoken at this instant to verify
                frame = await self._frames.extract_at(video_path, midpoint)
                verdict = await self._vision.inspect(
                    frame, narration=beat.narration, beat_id=beat.id
                )
                if not verdict.matches:
                    raise SyncGateError(beat.id, reason=verdict.reason)
        _logger.info("sync_gate.passed", scenes=len(contract.scenes))
