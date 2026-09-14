"""Actual Storage and PostgREST service clients, including anonymous access denial."""

import os
from uuid import uuid4

import httpx
import pytest
from lunaris_live.voice.persistence.supabase_audio_store import SupabaseVoiceAudioStore

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"),
        reason="local Storage credentials not configured",
    ),
]


@pytest.mark.asyncio
async def test_generated_pcm_is_private_in_real_storage_and_deleted_through_api():
    url = os.environ["LOCAL_SUPABASE_URL"]
    store = SupabaseVoiceAudioStore(url=url, key=os.environ["LOCAL_SUPABASE_SERVICE_KEY"])
    key = f"{uuid4().hex}.pcm"
    pcm = b"\0\0" * 240
    try:
        await store.put(key, pcm)
        assert await store.get(key) == pcm
        async with httpx.AsyncClient() as client:
            public = await client.get(f"{url}/storage/v1/object/public/live-voice/{key}")
            assert public.status_code in (400, 403, 404)
            anonymous = await client.get(
                f"{url}/storage/v1/object/authenticated/live-voice/{key}",
                headers={"Authorization": f"Bearer {os.environ['LOCAL_SUPABASE_ANON_KEY']}"},
            )
            assert anonymous.status_code in (400, 401, 403, 404)
    finally:
        await store.delete(key)
    async with httpx.AsyncClient() as client:
        missing = await client.get(
            f"{url}/storage/v1/object/authenticated/live-voice/{key}",
            headers={"Authorization": f"Bearer {os.environ['LOCAL_SUPABASE_SERVICE_KEY']}"},
        )
        assert missing.status_code in (400, 404)


@pytest.mark.asyncio
async def test_independent_service_instances_replay_without_new_provider_admission():
    from dataclasses import replace

    import psycopg
    from lunaris_live.voice.models.operation import VoiceOperation
    from lunaris_live.voice.persistence.schemas.result import VoiceResult
    from lunaris_live.voice.persistence.supabase_ledger import SupabaseVoiceLedger

    from supabase import create_client

    owner, sid = str(uuid4()), uuid4().hex
    url, key = os.environ["LOCAL_SUPABASE_URL"], os.environ["LOCAL_SUPABASE_SERVICE_KEY"]
    first = SupabaseVoiceLedger(client=create_client(url, key))
    second = SupabaseVoiceLedger(client=create_client(url, key))
    operation = VoiceOperation(sid, owner, uuid4(), "request", 1, "r")
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as setup:
        setup.execute("insert into auth.users(id) values (%s)", (owner,))
        setup.execute(
            "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
            "values (%s,%s,'g','active',1,jsonb_build_object('startedAt',now(),'turns',"
            '\'[{"seq":1,"runId":"r","tutor":"Try this"}]\'::jsonb))',
            (sid, owner),
        )
        try:
            admitted = await first.claim(
                operation, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1
            )
            assert admitted.status == "started"
            assert (
                await second.claim(
                    operation, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1
                )
            ).status == "in_progress"
            result = VoiceResult(text="An answer", provider="test", model="test")
            assert await first.complete(operation, admitted.token, result)
            replay = await second.claim(
                operation, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1
            )
            assert replay.status == "completed" and replay.result == result
            with pytest.raises(FileNotFoundError):
                await second.claim(
                    replace(operation, owner_id=str(uuid4())),
                    kind="transcription",
                    fingerprint="a" * 64,
                    reserve_usd=0.1,
                )
        finally:
            setup.execute("delete from auth.users where id=%s", (owner,))


@pytest.mark.asyncio
async def test_real_auth_account_deletion_keeps_private_audio_tombstone():
    import json

    import psycopg

    sid = uuid4().hex
    url, key = os.environ["LOCAL_SUPABASE_URL"], os.environ["LOCAL_SUPABASE_SERVICE_KEY"]
    headers = {"Authorization": f"Bearer {key}", "apikey": key}
    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{url}/auth/v1/admin/users",
            headers=headers,
            json={"email": f"{sid}@example.test", "password": uuid4().hex},
        )
        assert created.status_code == 200
        owner = created.json()["id"]
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as setup:
            setup.execute(
                "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
                "values (%s,%s,'g','active',1,jsonb_build_object('startedAt',"
                "now(),'turns',%s::jsonb))",
                (sid, owner, json.dumps([{"seq": 1, "runId": "r", "tutor": "Try this"}])),
            )
            try:
                request = {
                    "operation_id": str(uuid4()),
                    "kind": "speech",
                    "turn_seq": 1,
                    "source_run_id": "r",
                    "fingerprint": "a" * 64,
                    "reserve_usd": 0.1,
                }
                started = setup.execute(
                    "select public.claim_live_voice(%s,%s,%s)", (owner, sid, json.dumps(request))
                ).fetchone()[0]
                deleted = await client.delete(f"{url}/auth/v1/admin/users/{owner}", headers=headers)
                assert deleted.status_code == 200
                assert (
                    setup.execute(
                        "select count(*) from public.live_voice_audio_cleanup where object_key=%s",
                        (started["audio_key"],),
                    ).fetchone()[0]
                    == 1
                )
            finally:
                setup.execute("delete from auth.users where id=%s", (owner,))
