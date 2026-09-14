import asyncio
import json
import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.operation import VoiceOperation
from lunaris_live.voice.persistence.audio_cleanup import VoiceAudioCleanup
from lunaris_live.voice.persistence.schemas.result import VoiceResult
from lunaris_live.voice.persistence.supabase_audio_store import SupabaseVoiceAudioStore
from lunaris_live.voice.persistence.supabase_ledger import SupabaseVoiceLedger

from supabase import create_client

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY") or not os.getenv("SUPABASE_DB_URL"),
        reason="Local database and Storage credentials required",
    ),
]


@pytest.fixture
def voice_session() -> Iterator[tuple[psycopg.Connection, VoiceOperation]]:
    owner, sid = str(uuid4()), uuid4().hex
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as database:
        database.execute("insert into auth.users(id) values (%s)", (owner,))
        database.execute(
            "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
            "values (%s,%s,'voice-resilience','active',1,jsonb_build_object('startedAt',"
            "clock_timestamp(),'turns',%s::jsonb))",
            (sid, owner, json.dumps([{"seq": 1, "runId": "r", "tutor": "Current tutor text"}])),
        )
        try:
            yield database, VoiceOperation(sid, owner, uuid4(), "resilience-run", 1, "r")
        finally:
            database.execute("delete from auth.users where id=%s", (owner,))


def ledger() -> SupabaseVoiceLedger:
    return SupabaseVoiceLedger(
        client=create_client(
            os.environ["LOCAL_SUPABASE_URL"],
            os.environ["LOCAL_SUPABASE_SERVICE_KEY"],
        )
    )


@pytest.mark.asyncio
async def test_independent_replicas_share_one_paid_claim_and_never_reclaim_after_restart(
    voice_session: tuple[psycopg.Connection, VoiceOperation],
) -> None:
    database, operation = voice_session
    replicas = [ledger() for _ in range(8)]

    # Act: all replicas race with precisely the same operation identity.
    claims = await asyncio.gather(
        *(
            replica.claim(operation, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
            for replica in replicas
        )
    )

    # Assert: only one could invoke a provider; expiry does not grant another invocation.
    assert [claim.status for claim in claims].count("started") == 1
    assert [claim.status for claim in claims].count("in_progress") == 7
    assert database.execute(
        "select count(*),sum(reserve_usd) from public.live_voice_operations where session_id=%s",
        (operation.session_id,),
    ).fetchone() == (1, Decimal("0.1"))
    database.execute(
        "update public.live_voice_operations set expires_at=now()-interval '1 second' "
        "where session_id=%s",
        (operation.session_id,),
    )
    restarted = ledger()
    assert (
        await restarted.claim(
            operation,
            kind="transcription",
            fingerprint="a" * 64,
            reserve_usd=0.1,
        )
    ).status == "indeterminate"
    token = next(claim.token for claim in claims if claim.status == "started")
    assert not await restarted.complete(
        operation,
        token,
        VoiceResult(text="Late provider answer", provider="fixture", model="v1"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["expired", "deleted"])
async def test_real_cleanup_removes_private_pcm_without_allowing_paid_regeneration(
    voice_session: tuple[psycopg.Connection, VoiceOperation],
    cause: str,
) -> None:
    database, operation = voice_session
    receipts = ledger()
    audio = SupabaseVoiceAudioStore(
        url=os.environ["LOCAL_SUPABASE_URL"],
        key=os.environ["LOCAL_SUPABASE_SERVICE_KEY"],
    )
    claim = await receipts.claim(operation, kind="speech", fingerprint="b" * 64, reserve_usd=0.1)
    assert claim.token is not None and claim.audio_key is not None
    key = claim.audio_key
    try:
        await audio.put(key, b"\0\1" * 240)
        assert await receipts.complete(
            operation,
            claim.token,
            VoiceResult(
                audio_key=key,
                audio_bytes=480,
                sample_rate=24000,
                provider="fixture",
                model="v1",
            ),
        )
        if cause == "deleted":
            database.execute(
                "delete from public.live_sessions where id=%s", (operation.session_id,)
            )
        else:
            database.execute(
                "update public.live_voice_operations set created_at=now()-interval '2 days' "
                "where session_id=%s",
                (operation.session_id,),
            )
            database.execute(
                "update public.live_voice_audio_cleanup "
                "set cleanup_after=now()-interval '1 second' "
                "where object_key=%s",
                (key,),
            )

        # Act: reconstruct the maintenance worker as after an API restart.
        cleanup = VoiceAudioCleanup(
            audio,
            client=create_client(
                os.environ["LOCAL_SUPABASE_URL"],
                os.environ["LOCAL_SUPABASE_SERVICE_KEY"],
            ),
        )
        assert await cleanup.run_once() >= 1

        # Assert: actual bytes and tombstone are gone; the receipt never authorizes more billing.
        with pytest.raises(VoiceError):
            await audio.get(key)
        assert database.execute(
            "select count(*) from public.live_voice_audio_cleanup where object_key=%s",
            (key,),
        ).fetchone() == (0,)
        if cause == "deleted":
            with pytest.raises(FileNotFoundError):
                await ledger().claim(
                    operation, kind="speech", fingerprint="b" * 64, reserve_usd=0.1
                )
        else:
            assert (
                await ledger().claim(
                    operation,
                    kind="speech",
                    fingerprint="b" * 64,
                    reserve_usd=0.1,
                )
            ).status == "unavailable"
            assert database.execute(
                "select result from public.live_voice_operations where session_id=%s",
                (operation.session_id,),
            ).fetchone() == (None,)
    finally:
        await audio.delete(key)
