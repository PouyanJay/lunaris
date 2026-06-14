import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from lunaris_video.errors import VideoPipelineError
from lunaris_video.rendering.sandbox import run_sandboxed
from lunaris_video.schemas import BeatTiming, SceneTiming, TimingManifest, VideoContract, VoiceSpec

_logger = structlog.get_logger(__name__)

# Speaks one beat: (text, previous_text, next_text) -> audio bytes. The neighbour text keeps the
# separate per-beat clips sounding like one take (the skill's prosody-continuity rule). Default =
# the ElevenLabs TTS HTTP call; injectable so the orchestration tests skip the network.
ElevenLabsTtsClient = Callable[[str, str | None, str | None], Awaitable[bytes]]
# Measures a written clip's duration in seconds. Default = ffprobe (the render extra); injectable.
DurationMeasurer = Callable[[Path], Awaitable[float]]

# The skill's synthesize constants (scripts/narration.py) — kept identical so the measured manifest
# lines up beat-for-beat with the estimate it replaces.
_PAD_S = 0.15
_MIN_BEAT_S = 0.6

_ELEVENLABS_TTS_URL = (
    "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
)
_TTS_TIMEOUT_S = 120.0
_FFPROBE_TIMEOUT_S = 30.0


class ElevenLabsSpeechSynthesizer:
    """The real ``ISpeechSynthesizer``: ElevenLabs per-beat TTS + measured timing (skill Stage 2.5).

    One clip per beat, the neighbouring beats' narration passed as previous/next text so the clips
    sound like one continuous take, one ``voice_id`` per course. Measured durations (ffprobe) drive
    every on-screen window. The TTS call and the measurement are injectable seams — the live path
    needs an ElevenLabs key + ffmpeg, so it self-skips under hermetic tests while the per-beat
    orchestration is exercised with fakes.
    """

    def __init__(
        self,
        *,
        api_key: str,
        tts_client: ElevenLabsTtsClient | None = None,
        measure: DurationMeasurer | None = None,
    ) -> None:
        self._api_key = api_key
        self._tts_client = tts_client
        self._measure = measure or _ffprobe_duration

    async def synthesize(
        self, contract: VideoContract, *, voice: VoiceSpec, audio_dir: Path
    ) -> TimingManifest:
        await asyncio.to_thread(audio_dir.mkdir, parents=True, exist_ok=True)
        speak = self._tts_client or _elevenlabs_tts(self._api_key, voice)
        neighbours = _prosody_neighbours(contract)
        scenes: dict[str, SceneTiming] = {}
        for scene in contract.scenes:
            beats: list[BeatTiming] = []
            total = 0.0
            for beat in scene.beats:
                if beat.narration:
                    previous, following = neighbours[(scene.id, beat.id)]
                    audio_bytes = await speak(beat.narration, previous, following)
                    clip = f"{scene.id}_{beat.id}.mp3"
                    await asyncio.to_thread((audio_dir / clip).write_bytes, audio_bytes)
                    audio_s = round(await self._measure(audio_dir / clip), 2)
                else:
                    audio_s, clip = 0.0, None
                floor = beat.min_visual_s if beat.min_visual_s is not None else _MIN_BEAT_S
                anim_s = round(max(audio_s + (_PAD_S if beat.narration else 0.0), floor), 2)
                beats.append(
                    BeatTiming(
                        id=beat.id, audio_s=audio_s, anim_s=anim_s, audio=clip, estimated=False
                    )
                )
                total += anim_s
            scenes[scene.id] = SceneTiming(beats=beats, total_s=round(total, 2))
        _logger.info("speech_synth.synthesized", scenes=len(scenes), voice_id=voice.voice_id)
        return TimingManifest(scenes)


def _prosody_neighbours(
    contract: VideoContract,
) -> dict[tuple[str, str], tuple[str | None, str | None]]:
    """For each spoken beat, the previous/next spoken narration (spanning scene boundaries) — the
    continuity hints that keep separate per-beat clips sounding like one take."""
    ordered = [(scene, beat) for scene in contract.scenes for beat in scene.beats]
    spoken_indices = [index for index, (_, beat) in enumerate(ordered) if beat.narration]
    neighbours: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for rank, index in enumerate(spoken_indices):
        scene, beat = ordered[index]
        previous = ordered[spoken_indices[rank - 1]][1].narration if rank > 0 else None
        is_last = rank == len(spoken_indices) - 1
        following = None if is_last else ordered[spoken_indices[rank + 1]][1].narration
        neighbours[(scene.id, beat.id)] = (previous, following)
    return neighbours


def _elevenlabs_tts(api_key: str, voice: VoiceSpec) -> ElevenLabsTtsClient:
    """The default TTS seam: the ElevenLabs text-to-speech HTTP call for one beat (skill specifics
    in references/narration-sync.md — previous/next text are the prosody-continuity hints)."""

    async def speak(text: str, previous: str | None, following: str | None) -> bytes:
        import httpx

        body: dict[str, object] = {
            "text": text,
            "model_id": voice.model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        if previous:
            body["previous_text"] = previous
        if following:
            body["next_text"] = following
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT_S) as client:
            response = await client.post(
                _ELEVENLABS_TTS_URL.format(voice_id=voice.voice_id),
                headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
                json=body,
            )
            response.raise_for_status()
            return response.content

    return speak


async def _ffprobe_duration(path: Path) -> float:
    """Measure a clip's duration in seconds via ffprobe, in the hardened sandbox (the live path —
    needs the render extra). The output is a single float line, so the stdout tail carries it."""
    argv = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        path.name,
    ]
    result = await run_sandboxed(argv, cwd=path.parent, timeout_s=_FFPROBE_TIMEOUT_S)
    if not result.succeeded:
        raise VideoPipelineError(f"ffprobe failed for {path.name}: {result.stderr_tail}")
    try:
        return float(result.stdout_tail.strip())
    except ValueError as exc:
        # A duration-less container reports "N/A"; surface which clip rather than a bare ValueError.
        measured = result.stdout_tail.strip()
        raise VideoPipelineError(
            f"ffprobe returned a non-numeric duration for {path.name}: {measured!r}"
        ) from exc
