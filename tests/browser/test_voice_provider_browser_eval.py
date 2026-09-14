"""Opt-in provider/browser evaluation; microphone input is prerecorded synthetic audio."""

import asyncio
import base64
import importlib
import io
import json
import os
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.read_audio import read_audio
from playwright.async_api import Locator, Page, async_playwright, expect
from test_sim_authenticated import login
from test_sim_roundtrip import servers  # noqa: F401
from test_voice_copilot import copilot  # noqa: F401


async def test_provider_browser_fixture_enforces_paid_call_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUNARIS_VOICE_BROWSER_OFFLINE", "1")
    fixture = importlib.import_module("voice_provider_app")
    provider = fixture._CappedProvider()
    for _ in range(3):
        assert b"".join([chunk async for chunk in provider.speak("Synthetic words", run_id="test")])
    with pytest.raises(VoiceError):
        _ = [chunk async for chunk in provider.speak("Must refuse", run_id="test")]
    audio = read_audio(fixture._offline_wav())
    for _ in range(2):
        assert (await provider.transcribe(audio, run_id="test")).text
    with pytest.raises(VoiceError):
        await provider.transcribe(audio, run_id="test")
    assert provider.started == {"tts": 3, "stt": 2}


async def _install_recording(page: Page) -> None:
    if os.getenv("LUNARIS_VOICE_BROWSER_OFFLINE") == "1":
        fixture = importlib.import_module("voice_provider_app")
        data = fixture._offline_wav()
    else:
        data = await asyncio.to_thread(Path(os.environ["LUNARIS_VOICE_BROWSER_WAV"]).read_bytes)
    with wave.open(io.BytesIO(data), "rb") as source:
        assert source.getnchannels() == 1 and source.getsampwidth() == 2
        assert 0 < source.getnframes() / source.getframerate() <= 30
    encoded = base64.b64encode(data).decode()
    await page.add_init_script(
        """(() => {
      window.evalMicrophones = [];
      window.evalPlayback = {started: 0, ended: 0};
      const createBufferSource = AudioContext.prototype.createBufferSource;
      AudioContext.prototype.createBufferSource = function() {
        const node = createBufferSource.call(this);
        const start = node.start.bind(node);
        node.start = (...args) => { window.evalPlayback.started++; return start(...args); };
        node.addEventListener('ended', () => { window.evalPlayback.ended++; });
        return node;
      };
      navigator.mediaDevices.getUserMedia = async () => {
        const context = new AudioContext();
        await context.resume();
        const bytes = Uint8Array.from(atob("""
        + json.dumps(encoded)
        + """), c => c.charCodeAt(0));
        const decoded = await context.decodeAudioData(bytes.buffer);
        const source = context.createBufferSource();
        source.buffer = decoded;
        const destination = context.createMediaStreamDestination();
        source.connect(destination);
        const state = { stream: destination.stream, done: false };
        window.evalMicrophones.push(state);
        source.onended = () => { state.done = true; };
        const track = destination.stream.getTracks()[0];
        const stop = track.stop.bind(track);
        track.stop = () => {
          if (track.readyState === 'ended') return;
          stop(); source.stop(); void context.close();
        };
        source.start(context.currentTime + 0.25);
        return destination.stream;
      };
    })();"""
    )


async def _listen(page: Page, voice: Locator, label: str) -> dict[str, Any]:
    started = await page.evaluate("window.evalPlayback.started")
    async with page.expect_response(lambda r: r.url.endswith("/voice/speech")) as received:
        await voice.get_by_role("button", name=label, exact=True).click()
    response = await received.value
    assert response.status == 200
    pcm = await response.body()
    assert pcm and len(pcm) % 2 == 0
    await expect(voice.get_by_role("button", name=label, exact=True)).to_be_enabled(timeout=60000)
    await expect(voice.get_by_role("alert")).to_have_count(0)
    assert await page.evaluate("window.evalPlayback.started") > started
    await page.wait_for_function("window.evalPlayback.ended === window.evalPlayback.started")
    return {
        "bytes": len(pcm),
        "request_id": response.headers.get("x-request-id"),
        "source": response.request.post_data_json["source"],
    }


@pytest.mark.browser
@pytest.mark.skipif(
    os.getenv("LUNARIS_RUN_VOICE_BROWSER_EVAL") != "1",
    reason="Explicit bounded provider eval opt-in required",
)
@pytest.mark.parametrize(
    "servers",
    [{"app": "voice_provider_app", "auth": True, "practice": True}],
    indirect=True,
)
async def test_real_provider_copilot_simulator_and_reviewed_draft(
    servers: tuple[str, str],  # noqa: F811
    copilot: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    api, web = servers
    output = Path(os.environ.get("LUNARIS_VOICE_BROWSER_OUTPUT", str(tmp_path)))
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    evidence: dict[str, Any] = {"status": "running", "prerecorded_synthetic_microphone": True}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await login(browser)
        await _install_recording(page)
        try:
            async with page.expect_response(
                lambda r: r.url.endswith("/api/live/sessions") and r.request.method == "POST"
            ) as opened:
                await page.goto(f"{web}/tests/voice-session.html?api={api}&copilot={copilot}")
            session = await (await opened.value).json()
            sid = session["sessionId"]
            token = await page.evaluate(
                "JSON.parse(localStorage.getItem('sb-identity-auth-token')).access_token"
            )
            voice = page.get_by_role("region", name="Voice controls")
            await expect(voice.get_by_role("button", name="Speak", exact=True)).to_be_enabled()
            assert await page.evaluate("window.evalMicrophones.length") == 0
            evidence["tutor_speech"] = await _listen(page, voice, "Read aloud")
            frame = page.frame_locator("iframe").frame_locator("iframe")
            await frame.get_by_label("x value", exact=True).press("ArrowLeft")
            async with page.expect_response(lambda r: r.url.endswith("/sim")) as reacted:
                await frame.get_by_role("button", name="Discuss this state").click()
            reaction = await (await reacted.value).json()
            evidence["reaction_speech"] = await _listen(page, voice, "Read reaction")
            assert (
                evidence["reaction_speech"]["source"]["exchangeSequence"]
                == reaction["event"]["sequence"]
            )
            async with httpx.AsyncClient(
                base_url=api, headers={"Authorization": f"Bearer {token}"}
            ) as client:
                before = (await client.get(f"/api/live/sessions/{sid}")).json()
                await voice.get_by_role("button", name="Speak", exact=True).click()
                await expect(voice.get_by_role("button", name="Finish recording")).to_be_visible()
                await page.wait_for_function("window.evalMicrophones.at(-1).done", timeout=45000)
                async with page.expect_response(
                    lambda r: "/voice/transcriptions?" in r.url
                ) as transcribed:
                    await voice.get_by_role("button", name="Finish recording").click()
                response = await transcribed.value
                assert response.status == 200
                transcript = await response.json()
                draft = page.get_by_role("textbox", name="Your answer").last
                await expect(draft).to_have_value(transcript["text"], timeout=15000)
                assert transcript["text"].strip()
                assert (await client.get(f"/api/live/sessions/{sid}")).json() == before
                evidence["transcription"] = transcript
                await page.screenshot(path=str(output / "reviewed-draft.png"), full_page=True)
                after = before
                for _ in range(7):
                    if after["status"] == "closed":
                        break
                    await draft.fill(
                        "Explain proportional scaling: when x doubles, y doubles "
                        "because y is twice x."
                    )
                    async with page.expect_response(
                        lambda r: r.url.endswith("/agent/live/run") and r.request.method == "POST"
                    ) as answered:
                        await draft.press("Control+Enter")
                    assert (await answered.value).status == 200
                    await (await answered.value).finished()
                    after = (await client.get(f"/api/live/sessions/{sid}")).json()
                assert after["status"] == "closed"
                await expect(voice.get_by_role("button", name="Speak", exact=True)).to_have_count(0)
                evidence["goodbye_speech"] = await _listen(page, voice, "Read aloud")
                assert (await client.get(f"/api/live/sessions/{sid}")).json() == after
                evidence["turns"] = len(after["turns"])
            assert await page.evaluate(
                "window.evalMicrophones.every(m => "
                "m.stream.getTracks().every(t => t.readyState === 'ended'))"
            )
            async with httpx.AsyncClient(base_url=api) as client:
                evidence["provider"] = (await client.get("/test/voice-eval")).json()
            assert evidence["provider"]["calls_started"] == {"tts": 3, "stt": 1}
            run_ids = {metric["run_id"] for metric in evidence["provider"]["metrics"]}
            for kind in ("tutor_speech", "reaction_speech", "goodbye_speech"):
                assert evidence[kind]["request_id"] in run_ids
            evidence["status"] = "completed"
        except BaseException as exc:
            evidence.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            try:
                await _save_evidence(api, output, evidence)
            finally:
                await browser.close()


async def _save_evidence(api: str, output: Path, evidence: dict[str, Any]) -> None:
    # Preserve the original test failure even if the server or artifact disk also failed.
    try:
        if "provider" not in evidence:
            async with httpx.AsyncClient(base_url=api, timeout=5) as client:
                evidence["provider"] = (await client.get("/test/voice-eval")).json()
    except (httpx.HTTPError, ValueError) as exc:
        evidence["evidence_fetch_error"] = type(exc).__name__
    try:
        await asyncio.to_thread(
            (output / "browser-evidence.json").write_text,
            json.dumps(evidence, indent=2) + "\n",
        )
    except OSError:
        if evidence["status"] == "completed":
            raise
