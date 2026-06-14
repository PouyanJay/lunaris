from pathlib import Path
from typing import Protocol

from lunaris_video.schemas import TimingManifest, VideoContract, VoiceSpec


class ISpeechSynthesizer(Protocol):
    """Synthesizes per-beat narration and measures it into a ``TimingManifest`` — the VOICE seam.

    Audio drives video (the pinned ``narration-sync`` design): the synthesizer speaks each beat
    (one clip per beat, the neighbouring beats' text passed for prosody continuity, one voice per
    course), writes the clips under ``audio_dir``, and returns the MEASURED manifest the CODE stage
    then renders to. The estimate path (``estimate_timing``) returns the same manifest shape, so a
    contract renders silent or narrated with no re-plan. A silent beat (empty narration) speaks
    nothing — its on-screen window stays the visual floor.
    """

    async def synthesize(
        self, contract: VideoContract, *, voice: VoiceSpec, audio_dir: Path
    ) -> TimingManifest: ...
