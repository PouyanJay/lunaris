"""Cost-metering coverage for the video paid seams (course-cost-metering, T6 voice + T7 render).

Both run in the video worker (which enters a cost_scope in _render). These drive the real
``ElevenLabsSpeechSynthesizer`` (via injected fake TTS + measure) and the real ``SceneRenderer``
(via a monkeypatched sandbox) inside a ``cost_scope`` and assert the recorded provider / unit.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_runtime.metering import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostProvider
from lunaris_video.models.sandbox_result import SandboxResult
from lunaris_video.rendering import scene_renderer as sr
from lunaris_video.schemas import SceneContracts, VoiceSpec
from lunaris_video.voice import ElevenLabsSpeechSynthesizer

_VOICE = VoiceSpec(provider="elevenlabs", voice_id="v-test", model="eleven_multilingual_v2")


def _scope() -> CostScope:
    return CostScope(run_id="r", course_id="c", price_book=PriceBook.current())


async def test_voice_synthesis_records_character_cost(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — a real narrated contract; fake the TTS call + duration probe so it runs offline.
    contract = make_lesson_contract()
    total_chars = sum(
        len(beat.narration) for scene in contract.scenes for beat in scene.beats if beat.narration
    )
    assert total_chars > 0, "precondition: the contract has narration to bill"

    async def fake_speak(text: str, previous: str, following: str) -> bytes:
        return b"MP3"

    async def fake_measure(path: Path) -> float:
        return 1.0

    synth = ElevenLabsSpeechSynthesizer(api_key="k", tts_client=fake_speak, measure=fake_measure)
    scope = _scope()

    # Act
    with cost_scope(scope):
        await synth.synthesize(contract, voice=_VOICE, audio_dir=tmp_path)

    # Assert — one ElevenLabs cost for the whole narration, billed per character.
    voice_entries = [e for e in scope.entries if e.provider is CostProvider.ELEVENLABS]
    assert len(voice_entries) == 1
    assert voice_entries[0].component == "voice"
    assert voice_entries[0].usage == {"chars": total_chars}
    assert voice_entries[0].amount == pytest.approx(total_chars * 0.0003)


async def test_scene_render_records_compute_seconds(monkeypatch, tmp_path: Path) -> None:
    # Arrange — a fake sandbox so no real Manim runs; a failed render still spent the compute.
    async def fake_sandboxed(argv: list[str], *, cwd: Path, timeout_s: float) -> SandboxResult:
        return SandboxResult(returncode=1, stdout_tail="", stderr_tail="boom", timed_out=False)

    monkeypatch.setattr(sr, "run_sandboxed", fake_sandboxed)
    scene_file = tmp_path / "scene.py"
    scene_file.write_text("# scene")
    scope = _scope()

    # Act
    with cost_scope(scope):
        await sr.SceneRenderer().render(scene_file, "MyScene")

    # Assert — render compute is metered (as MANIM vCPU-seconds) even on a failed render.
    entry = scope.entries[0]
    assert entry.provider is CostProvider.MANIM
    assert entry.component == "render"
    assert list(entry.usage) == ["compute_seconds"]
    assert entry.usage["compute_seconds"] >= 0.0
