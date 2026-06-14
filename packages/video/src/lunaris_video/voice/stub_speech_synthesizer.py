import asyncio
from pathlib import Path

from lunaris_video.schemas import BeatTiming, SceneTiming, TimingManifest, VideoContract, VoiceSpec

# A placeholder clip — the stub never renders audio; tests only assert a clip landed on disk.
_PLACEHOLDER_CLIP = b"stub-audio-clip"


class StubSpeechSynthesizer:
    """A deterministic ``ISpeechSynthesizer`` for hermetic tests — a measured-shape manifest with no
    key, network, or ffmpeg.

    Each spoken beat gets a placeholder clip on disk and a duration from a fixed per-word rate
    DISTINCT from the WPM estimate, so a test can prove measured timings replace estimated ones
    (audio drove the video). Silent beats keep their visual floor and speak nothing. The manifest is
    the same ``TimingManifest`` the estimate emits — only ``estimated=False`` and the clip paths
    differ — so the silent and narrated paths render from one contract.
    """

    # A deliberately non-WPM rate so a stubbed "measurement" never coincides with the estimate.
    _SECONDS_PER_WORD = 0.6
    _LEAD_IN_S = 0.1
    _PAD_S = 0.15
    _MIN_BEAT_S = 0.6

    async def synthesize(
        self, contract: VideoContract, *, voice: VoiceSpec, audio_dir: Path
    ) -> TimingManifest:
        await asyncio.to_thread(audio_dir.mkdir, parents=True, exist_ok=True)
        scenes: dict[str, SceneTiming] = {}
        for scene in contract.scenes:
            beats: list[BeatTiming] = []
            total = 0.0
            for beat in scene.beats:
                words = len(beat.narration.split())
                if words:
                    audio_s = round(words * self._SECONDS_PER_WORD + self._LEAD_IN_S, 2)
                    clip = f"{scene.id}_{beat.id}.mp3"
                    await asyncio.to_thread((audio_dir / clip).write_bytes, _PLACEHOLDER_CLIP)
                else:
                    audio_s, clip = 0.0, None
                floor = beat.min_visual_s if beat.min_visual_s is not None else self._MIN_BEAT_S
                anim_s = round(max(audio_s + (self._PAD_S if words else 0.0), floor), 2)
                beats.append(
                    BeatTiming(
                        id=beat.id, audio_s=audio_s, anim_s=anim_s, audio=clip, estimated=False
                    )
                )
                total += anim_s
            scenes[scene.id] = SceneTiming(beats=beats, total_s=round(total, 2))
        return TimingManifest(scenes)
