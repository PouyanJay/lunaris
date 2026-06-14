from pydantic import RootModel

from lunaris_video.schemas.base import ContractModel


class BeatTiming(ContractModel):
    """One beat's resolved timing — the skill's ``timing.json`` beat shape, byte-for-byte.

    ``audio_s`` is the spoken length (0 for a silent beat). ``anim_s`` is the on-screen window the
    scene code must fill: ``max(audio_s, min_visual_s)`` for the estimate (the inter-beat pause is
    already inside ``audio_s``) and ``max(audio_s + pad, min_visual_s)`` for measured TTS (where
    ``audio_s`` is the raw clip length). ``audio`` is the clip path once synthesized, else ``None``.
    ``estimated`` is ``True`` for the WPM estimate (silent, voice-ready) and ``False`` for measured
    TTS. The field set is identical in both modes — only the values differ — so a contract renders
    silent or narrated with no re-plan.
    """

    id: str
    audio_s: float
    anim_s: float
    audio: str | None = None
    estimated: bool


class SceneTiming(ContractModel):
    """One scene's beats and the sum of their on-screen windows (the scene's total duration)."""

    beats: list[BeatTiming]
    total_s: float


class TimingManifest(RootModel[dict[str, SceneTiming]]):
    """The per-scene, per-beat timing the whole render reads — the audio-drives-video manifest.

    Keyed by scene id (the skill's ``timing.json`` top-level shape). The estimate path (silent,
    voice-ready) and the measured path (ElevenLabs synthesis) produce the SAME shape; codegen,
    captions, and Gate D all read this one manifest, which is what lets silent and narrated render
    from one contract. ``model_dump_json`` round-trips to the exact on-disk ``timing.json`` bytes.
    """

    def __getitem__(self, scene_id: str) -> SceneTiming:
        return self.root[scene_id]

    def scene_ids(self) -> list[str]:
        return list(self.root)

    @property
    def total_s(self) -> float:
        """The whole video's playback duration — the sum of every scene's on-screen window."""
        return sum(scene.total_s for scene in self.root.values())

    @property
    def is_voiced(self) -> bool:
        """True once any beat has a synthesized clip — the measured path. Silent (estimate)
        manifests carry no audio, so the assembler skips the mux and ships no captions."""
        return any(beat.audio is not None for scene in self.root.values() for beat in scene.beats)
