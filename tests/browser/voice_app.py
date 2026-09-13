"""Offline speech provider on real HTTP/session layers; never loaded by production."""

import io
import math
import struct
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.throttle import LiveSessionThrottle
from lunaris_api.live.voice.dependencies import get_live_voice_service
from lunaris_api.live.voice.session_reader import StoredVoiceSessions
from lunaris_live.graph import MemoryGraphStore, StubGraphCompiler
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor
from lunaris_live.session.schema import Session
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.models.transcription import Transcription
from lunaris_live.voice.service import VoiceService


class _FixtureVoiceProvider:
    def __init__(self) -> None:
        self.transcriptions: list[dict[str, str]] = []
        self.speech: list[dict[str, str]] = []

    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription:
        assert 0 < audio.duration_s <= 60
        self.transcriptions.append({"run_id": run_id})
        return Transcription("A fraction is a part of a whole.", "browser-fixture", "fixture-v1")

    async def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        self.speech.append({"text": text, "run_id": run_id})
        for start in range(0, 2400, 600):
            yield b"".join(
                struct.pack("<h", round(1000 * math.sin(2 * math.pi * 440 * n / 24000)))
                for n in range(start, start + 600)
            )


app = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-Session-Id", "X-Audio-Sample-Rate"],
)
graphs = MemoryGraphStore()
sessions = MemorySessionStore()
service = LiveSessionService(
    graphs,
    sessions,
    knowledge=MemoryKnowledgeStore(),
    tutor=StubTutor(),
    grader=StubGrader(),
    session_budget_s=1800,
    throttle=LiveSessionThrottle(open_daily_cap=100),
)
provider = _FixtureVoiceProvider()
voice = VoiceService(StoredVoiceSessions(sessions), provider)
app.dependency_overrides[get_settings] = lambda: Settings(
    pipeline="stub",
    course_dir=Path("/tmp/lunaris-voice-browser-test"),
    env_file=Path("/nonexistent/lunaris-browser-test.env"),
    cors_origins=("*",),
)
app.dependency_overrides[get_live_session_service] = lambda: service
app.dependency_overrides[get_live_voice_service] = lambda: voice


@app.post("/test/session")
async def fixture_session() -> Session:
    graph = await StubGraphCompiler().compile(
        "Fractions", graph_id=uuid4().hex, run_id="voice-browser-seed"
    )
    graphs.save(graph)
    return await service.start(graph.graph_id, session_id=uuid4().hex)


@app.get("/test/recording")
async def fixture_recording() -> Response:
    output = io.BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        recording.writeframes(b"\x00\x00" * 1600)
    return Response(output.getvalue(), media_type="audio/wav")


@app.get("/test/provider-calls")
async def fixture_calls() -> dict[str, list[dict[str, str]]]:
    return {"transcriptions": provider.transcriptions, "speech": provider.speech}
