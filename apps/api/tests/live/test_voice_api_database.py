"""Authenticated HTTP voice requests use real Postgres receipts, private Storage and costs."""

import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import psycopg
import pytest
from _auth import JWT_SECRET, auth_headers
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.voice.provider_dependencies import get_voice_provider
from lunaris_api.live.voice.storage_dependencies import resolve_voice_storage
from lunaris_live.session.schema import Session, SessionTurn
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
from test_live_voice_skeleton import recorded_wav

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"), reason="local database/storage not configured"
    ),
]


async def test_authenticated_voice_replay_persists_receipts_audio_and_usage(tmp_path, monkeypatch):
    owner, sid = str(uuid4()), uuid4().hex
    session = Session(
        session_id=sid,
        graph_id="voice-fixture",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                run_id="voice-source",
                tutor="HIPAA and EHR.",
                move={"kind": "introduce", "nodeId": "n", "reason": "fixture"},
            )
        ],
    )
    settings = settings_for(
        tmp_path,
        live_voice_enabled=True,
        supabase_url=os.environ["LOCAL_SUPABASE_URL"],
        supabase_service_role_key=os.environ["LOCAL_SUPABASE_SERVICE_KEY"],
        supabase_jwt_secret=JWT_SECRET,
    )
    monkeypatch.setenv("ELEVENLABS_API_KEY", "voice-fixture-key")
    monkeypatch.setenv("SUPABASE_URL", os.environ["LOCAL_SUPABASE_URL"])
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", os.environ["LOCAL_SUPABASE_SERVICE_KEY"])
    calls = []

    def provider_http(request):
        calls.append(request)
        assert request.headers["xi-api-key"] == "voice-fixture-key"
        if request.url.path.endswith("/speech-to-text"):
            return httpx.Response(200, json={"text": "A fraction is a part of a whole."})
        return httpx.Response(200, content=b"\x01\x00" * 240, headers={"content-type": "audio/pcm"})

    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as database:
        database.execute("insert into auth.users(id) values (%s)", (owner,))
        database.execute(
            "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
            "values (%s,%s,%s,'active',1,%s::jsonb)",
            (sid, owner, session.graph_id, session.model_dump_json(by_alias=True)),
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(provider_http)
            ) as provider_client:
                app = create_app()
                app.dependency_overrides[get_settings] = lambda: settings
                app.dependency_overrides[get_voice_provider] = lambda: ElevenLabsVoiceProvider(
                    client=provider_client
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    prefix = f"/api/live/sessions/{sid}/voice"
                    source = {"turnSeq": 1, "runId": "voice-source"}
                    payload = {"source": source, "operationId": str(uuid4())}
                    assert (await client.post(f"{prefix}/speech", json=payload)).status_code == 401
                    headers = {
                        **auth_headers(owner),
                        "Content-Type": "audio/wav",
                        "Idempotency-Key": str(uuid4()),
                    }
                    for _ in range(2):
                        response = await client.post(
                            f"{prefix}/transcriptions",
                            params=source,
                            content=recorded_wav(),
                            headers=headers,
                        )
                        assert response.status_code == 200, response.text
                    assert len(calls) == 1
                    for _ in range(2):
                        response = await client.post(
                            f"{prefix}/speech", json=payload, headers=auth_headers(owner)
                        )
                        assert response.status_code == 200, response.text
                        assert response.content == b"\x01\x00" * 240
                    assert len(calls) == 2
                    other = await client.post(
                        f"{prefix}/speech", json=payload, headers=auth_headers(str(uuid4()))
                    )
                    assert other.status_code == 404
                    assert len(calls) == 2
            receipts = database.execute(
                "select status,result from public.live_voice_operations where session_id=%s", (sid,)
            ).fetchall()
            assert len(receipts) == 2 and all(row[0] == "completed" for row in receipts)
            costs = database.execute(
                "select component,usage from public.cost_events "
                "where subject_id=%s order by component",
                (sid,),
            ).fetchall()
            assert costs == [
                ("live_voice_stt", {"audio_seconds": 0.1}),
                ("live_voice_tts", {"chars": len("Hippa and E-H-R.")}),
            ]
            persisted = database.execute(
                "select payload from public.live_sessions where id=%s", (sid,)
            ).fetchone()[0]
            assert persisted == json.loads(session.model_dump_json(by_alias=True))
        finally:
            rows = database.execute(
                "select result->>'audio_key' from public.live_voice_operations where session_id=%s",
                (sid,),
            ).fetchall()
            for (key,) in rows:
                if key:
                    await resolve_voice_storage(settings).audio.delete(key)
            database.execute("delete from auth.users where id=%s", (owner,))
