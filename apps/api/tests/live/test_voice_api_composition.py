"""Real voice admission, provider transport and replay compose through the HTTP API."""

from dataclasses import replace
from uuid import uuid4

import httpx
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.dependencies import optional_user_id
from lunaris_api.live.voice.provider_dependencies import get_voice_provider
from lunaris_live.voice.models.transcription import Transcription
from test_live_voice_skeleton import recorded_wav


async def test_enabled_voice_replays_owned_results_without_advancing_learning(tmp_path):
    class Provider:
        transcriptions = 0
        speeches = 0

        async def transcribe(self, audio, *, run_id):
            self.transcriptions += 1
            return Transcription("A part of a whole", "fixture", "fixture-v1")

        async def speak(self, text, *, run_id):
            self.speeches += 1
            yield b"\x01\x00" * 20
            yield b"\x02\x00" * 20

    provider = Provider()
    settings = replace(settings_for(tmp_path), live_voice_enabled=True)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[optional_user_id] = lambda: "voice-owner"
    app.dependency_overrides[get_voice_provider] = lambda: provider
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        graph = (await client.post("/api/live/graphs", json={"topic": "Fractions"})).json()
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
        prefix = f"/api/live/sessions/{session['sessionId']}"
        turn = session["turns"][-1]
        source = {"turnSeq": turn["seq"], "runId": turn["runId"]}
        operation = str(uuid4())
        headers = {"Content-Type": "audio/wav", "Idempotency-Key": operation}
        first = await client.post(
            f"{prefix}/voice/transcriptions", params=source, content=recorded_wav(), headers=headers
        )
        assert first.status_code == 200, first.text
        replay = await client.post(
            f"{prefix}/voice/transcriptions", params=source, content=recorded_wav(), headers=headers
        )
        assert replay.json() == first.json()
        assert provider.transcriptions == 1
        payload = {"source": source, "operationId": str(uuid4())}
        spoken = await client.post(f"{prefix}/voice/speech", json=payload)
        assert spoken.status_code == 200, spoken.text
        cached = await client.post(f"{prefix}/voice/speech", json=payload)
        assert cached.content == spoken.content == b"\x01\x00" * 20 + b"\x02\x00" * 20
        assert provider.speeches == 1
        assert (await client.get(prefix)).json() == session
        app.dependency_overrides[optional_user_id] = lambda: "other-owner"
        refused = await client.post(f"{prefix}/voice/speech", json=payload)
        assert refused.status_code == 404
        assert provider.speeches == 1
