import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
from lunaris_live.voice.read_audio import read_audio
from lunaris_runtime.credentials import run_credentials


def runner() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts/eval_live_voice.py"
    spec = importlib.util.spec_from_file_location("live_voice_evaluation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_word", [False, True])
async def test_eval_bounds_real_adapter_requests_and_retains_audio_metrics(
    tmp_path: Path,
    replace_word: bool,
) -> None:
    evaluation = runner()
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/speech-to-text"):
            assert b"RIFF" in request.content
            transcript = evaluation._TEXTS[0]
            if replace_word:
                transcript = transcript.replace("privacy", "information")
            return httpx.Response(200, json={"text": transcript})
        assert request.url.path.endswith("/JBFqnCBsd6RMkjVDRZzb/stream")
        assert json.loads(request.content)["model_id"] == "eleven_flash_v2_5"
        return httpx.Response(200, content=b"\x01\0" * 2400, headers={"content-type": "audio/pcm"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "test-key"}):
            await evaluation.run_evaluation(ElevenLabsVoiceProvider(client=client), tmp_path)
            with pytest.raises(FileExistsError):
                await evaluation.run_evaluation(ElevenLabsVoiceProvider(client=client), tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "completed"
    assert len(requests) == 3
    assert report["calls_started"] == {"tts": 2, "stt": 1}
    assert report["billed_cost_usd"] is None
    assert report["intelligibility"]["word_error_rate"] == pytest.approx(
        1 / 11 if replace_word else 0
    )
    assert report["intelligibility"]["human_rating"] is None
    assert report["speech"][0]["first_pcm_ms"] >= 0
    assert report["transcription"]["latency_ms"] >= 0
    assert report["transcription"]["model"] == "scribe_v2"
    assert [entry["model"] for entry in report["metered_usage"]] == [
        "eleven_flash_v2_5",
        "eleven_flash_v2_5",
        "scribe_v2",
    ]
    assert read_audio((tmp_path / "transcription-input.wav").read_bytes()).duration_s == 0.1
    assert (tmp_path / "speech-1.wav").is_file()
    assert (tmp_path / "speech-2.wav").is_file()


@pytest.mark.asyncio
async def test_eval_stops_after_first_provider_failure_without_retry_or_sensitive_error(
    tmp_path: Path,
) -> None:
    evaluation = runner()
    calls: list[httpx.Request] = []

    def reject(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, text="private-provider-response")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "test-key"}), pytest.raises(VoiceError):
            await evaluation.run_evaluation(ElevenLabsVoiceProvider(client=client), tmp_path)
    serialized = (tmp_path / "report.json").read_text()
    report = json.loads(serialized)
    assert report["status"] == "failed"
    assert report["calls_started"] == {"tts": 1, "stt": 0}
    assert len(calls) == 1
    assert "private-provider-response" not in serialized and "test-key" not in serialized


def test_default_cli_only_writes_a_plan_and_never_generates_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    script = Path(__file__).resolve().parents[3] / "scripts/eval_live_voice.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--output", str(tmp_path)],
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert json.loads((tmp_path / "plan.json").read_text())["status"] == "not_run"
    assert not (tmp_path / "report.json").exists()
    assert not list(tmp_path.glob("*.wav"))


@pytest.mark.asyncio
async def test_stuck_stream_close_has_its_own_deadline_and_records_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = runner()
    monkeypatch.setattr(evaluation, "_CLEANUP_TIMEOUT_S", 0.01, raising=False)
    closed = asyncio.Event()

    class StuckStream:
        sent = False

        def __aiter__(self) -> "StuckStream":
            return self

        async def __anext__(self) -> bytes:
            if self.sent:
                raise StopAsyncIteration
            self.sent = True
            return b"\0\0" * 2400

        async def aclose(self) -> None:
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

    class Provider:
        def speak(self, text: str, *, run_id: str) -> StuckStream:
            return StuckStream()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(evaluation.run_evaluation(Provider(), tmp_path), timeout=0.2)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["error_type"] == "TimeoutError"
    assert report["status"] == "failed"
    assert report["calls_started"] == {"tts": 1, "stt": 0}
    assert closed.is_set()


@pytest.mark.asyncio
async def test_existing_claim_without_report_refuses_before_any_provider_request(
    tmp_path: Path,
) -> None:
    evaluation = runner()
    (tmp_path / "attempt.claim").write_text("previous process may already have spent money")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "test-key"}), pytest.raises(FileExistsError):
            await evaluation.run_evaluation(ElevenLabsVoiceProvider(client=client), tmp_path)
    assert requests == []
    assert not (tmp_path / "report.json").exists()
