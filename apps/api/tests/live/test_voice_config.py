"""Voice rollout is explicit and its browser-visible transport metadata survives CORS."""

from uuid import uuid4

import httpx
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings


def test_voice_requires_explicit_operator_enable(monkeypatch):
    monkeypatch.setenv("LUNARIS_LIVE_VOICE_ENABLED", "true")
    get_settings.cache_clear()
    try:
        assert getattr(get_settings(), "live_voice_enabled", False) is True
    finally:
        get_settings.cache_clear()


async def test_voice_cors_exposes_audio_and_session_metadata(tmp_path):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/live/sessions/s/voice/speech",
            json={"source": {"turnSeq": 1, "runId": "r"}, "operationId": str(uuid4())},
            headers={"Origin": "http://localhost:5173"},
        )
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "x-audio-sample-rate" in exposed
    assert "x-session-id" in exposed
