"""Voice is a bounded adapter to a persisted session, never another answer path."""

import io
import json
import struct
import wave
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings


async def test_voice_is_explicitly_unavailable_until_configured(tmp_path):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/live/sessions/s/voice/speech",
            json={
                "source": {"turnSeq": 1, "runId": "r"},
                "operationId": str(uuid4()),
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "Voice is unavailable. Continue with text."


def recorded_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


async def test_voice_roundtrip_uses_owned_turn_without_advancing_until_text_is_sent(
    tmp_path, capsys
):
    from lunaris_api.dependencies import optional_user_id
    from lunaris_api.live.session.dependencies import _resolve_session_store
    from lunaris_api.live.voice.dependencies import get_live_voice_service
    from lunaris_api.live.voice.session_reader import StoredVoiceSessions
    from lunaris_live.voice.models.transcription import Transcription
    from lunaris_live.voice.service import VoiceService

    class FixtureProvider:
        def __init__(self):
            self.spoken = []

        async def transcribe(self, audio, *, run_id):
            assert audio.duration_s == 0.1
            return Transcription(
                text="Explain proportional scaling.", provider="fixture", model="fixture-v1"
            )

        async def speak(self, text, *, run_id):
            self.spoken.append(text)
            yield b"\x01\x00" * 800
            yield b"\x02\x00" * 800

    app = create_app()
    settings = settings_for(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    owner = "voice-learner"
    app.dependency_overrides[optional_user_id] = lambda: owner
    # Resolve the actual session dependency through the HTTP app. Voice delegates to this same
    # service for ownership and persisted-source reads; the provider alone is deterministic.
    provider = FixtureProvider()

    def voice_service():
        return VoiceService(StoredVoiceSessions(_resolve_session_store(settings)), provider)

    app.dependency_overrides[get_live_voice_service] = voice_service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        graph = (await client.post("/api/live/graphs", json={"topic": "Linear functions"})).json()
        opened = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert opened.status_code == 201, opened.text
        session = opened.json()
        sid = session["sessionId"]
        turn = session["turns"][-1]
        source = {"turnSeq": turn["seq"], "runId": turn["runId"]}
        capsys.readouterr()
        transcript = await client.post(
            f"/api/live/sessions/{sid}/voice/transcriptions",
            params=source,
            content=recorded_wav(),
            headers={
                "Content-Type": "audio/wav",
                "Idempotency-Key": str(uuid4()),
            },
        )
        assert transcript.status_code == 200, transcript.text
        assert transcript.json()["text"] == "Explain proportional scaling."
        assert transcript.json()["provider"] == "fixture"
        assert transcript.headers["X-Request-Id"]
        logs = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{")
        ]
        event = next(item for item in logs if item["event"] == "live.voice.transcribed")
        assert event["request_id"] == transcript.headers["X-Request-Id"]
        assert event["session_id"] == sid
        assert "Explain proportional scaling." not in json.dumps(logs)
        for invalid, status in [
            (b"not-wave", 422),
            (b"RIFF" + struct.pack("<I", 12) + b"WAVEJUNK" + struct.pack("<I", 100) + b"1234", 422),
            (recorded_wav()[:-2], 422),
            (b"x" * 1920045, 413),
        ]:
            rejected = await client.post(
                f"/api/live/sessions/{sid}/voice/transcriptions",
                params=source,
                content=invalid,
                headers={"Content-Type": "audio/wav", "Idempotency-Key": str(uuid4())},
            )
            assert rejected.status_code == status, rejected.text
            assert rejected.headers["X-Request-Id"]
            assert rejected.headers["Cache-Control"] == "no-store"
        assert (await client.get(f"/api/live/sessions/{sid}")).json() == session
        speech = await client.post(
            f"/api/live/sessions/{sid}/voice/speech",
            json={
                "source": source,
                "operationId": str(uuid4()),
            },
        )
        assert speech.status_code == 200, speech.text
        assert speech.headers["content-type"] == "audio/pcm"
        assert speech.headers["x-audio-sample-rate"] == "24000"
        assert speech.content == b"\x01\x00" * 800 + b"\x02\x00" * 800
        assert provider.spoken == [turn["tutor"]]
        owner = "other-learner"
        denied = await client.post(
            f"/api/live/sessions/{sid}/voice/speech",
            json={
                "source": source,
                "operationId": str(uuid4()),
            },
        )
        assert denied.status_code == 404
        assert len(provider.spoken) == 1
        owner = "voice-learner"
        answered = await client.post(
            f"/api/live/sessions/{sid}/turns",
            json={
                "answer": transcript.json()["text"],
                "answeringSeq": turn["seq"],
            },
        )
        assert answered.status_code == 200, answered.text
        assert len(answered.json()["turns"]) == 2
        assert answered.json()["turns"][0]["grade"] is not None
        assert answered.json()["turns"][0]["answer"] == transcript.json()["text"]
        stale = await client.post(
            f"/api/live/sessions/{sid}/voice/speech",
            json={
                "source": source,
                "operationId": str(uuid4()),
            },
        )
        assert stale.status_code == 409
        assert len(provider.spoken) == 1

        stored = _resolve_session_store(settings)
        expired = stored.load(sid, owner_id=owner).model_copy(
            update={"started_at": datetime.now(UTC) - timedelta(hours=2)}
        )
        stored.save(expired, owner_id=owner)
        current = expired.turns[-1]
        refused = await client.post(
            f"/api/live/sessions/{sid}/voice/speech",
            json={
                "source": {"turnSeq": current.seq, "runId": current.run_id},
                "operationId": str(uuid4()),
            },
        )
        assert refused.status_code == 409
        assert stored.load(sid, owner_id=owner) == expired
        assert len(provider.spoken) == 1
