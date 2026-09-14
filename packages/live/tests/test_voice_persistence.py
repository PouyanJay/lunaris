from datetime import UTC, datetime
from uuid import uuid4

import pytest
from lunaris_live.session.memory_session_store import MemorySessionStore
from lunaris_live.session.schema import Session, SessionTurn
from lunaris_live.voice.models.operation import VoiceOperation
from lunaris_live.voice.persistence.memory_ledger import MemoryVoiceLedger
from lunaris_live.voice.persistence.schemas.result import VoiceResult


def session():
    return Session(
        session_id="s",
        graph_id="g",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                run_id="r",
                tutor="Try this.",
                move={"kind": "introduce", "nodeId": "n", "reason": "start"},
            )
        ],
    )


def operation():
    return VoiceOperation("s", None, uuid4(), "request", 1, "r")


@pytest.mark.asyncio
async def test_completed_transcript_replays_without_another_claim():
    sessions = MemorySessionStore()
    sessions.save(session())
    ledger = MemoryVoiceLedger(sessions)
    op = operation()
    claim = await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    assert claim.status == "started"
    assert claim.token is not None
    result = VoiceResult(text="My answer", provider="test", model="test")
    assert await ledger.complete(op, claim.token, result)
    replay = await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    assert replay.status == "completed"
    assert replay.result == result
    assert replay.token is None


@pytest.mark.asyncio
async def test_claim_limits_and_expired_uncertain_receipt_never_rebill():
    from datetime import timedelta

    from lunaris_live.voice.persistence.models.limits import VoiceLimits

    now = datetime.now(UTC)
    sessions = MemorySessionStore()
    sessions.save(session())
    ledger = MemoryVoiceLedger(
        sessions, limits=VoiceLimits(concurrency=1, reserve_usd=0.15), clock=lambda: now
    )
    op = operation()
    claim = await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    assert (
        await ledger.claim(operation(), kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    ).status == "unavailable"
    now += timedelta(seconds=121)
    assert (
        await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    ).status == "indeterminate"
    assert not await ledger.complete(
        op, claim.token, VoiceResult(text="late", provider="test", model="test")
    )
    assert (
        await ledger.claim(operation(), kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    ).status == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "closed", "deleted", "advanced"])
async def test_completion_never_publishes_after_owner_or_session_changes(change):
    from dataclasses import replace

    from lunaris_live.session.schema import SessionStatus

    sessions = MemorySessionStore()
    original = session()
    sessions.save(original)
    ledger = MemoryVoiceLedger(sessions)
    op = operation()
    claim = await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    if change == "owner":
        op = replace(op, owner_id=str(uuid4()))
    if change == "deleted":
        sessions.delete("s")
    if change == "closed":
        sessions.save(original.model_copy(update={"status": SessionStatus.CLOSED}))
    if change == "advanced":
        sessions.save(
            original.model_copy(update={"turns": [original.turns[0].model_copy(update={"seq": 2})]})
        )
    assert not await ledger.complete(
        op, claim.token, VoiceResult(text="stale", provider="test", model="test")
    )


@pytest.mark.asyncio
async def test_uuid_cannot_replay_different_input_and_audio_key_is_fenced():
    from lunaris_live.voice.error import VoiceError

    sessions = MemorySessionStore()
    sessions.save(session())
    ledger = MemoryVoiceLedger(sessions)
    op = operation()
    claim = await ledger.claim(op, kind="speech", fingerprint="a" * 64, reserve_usd=0.1)
    assert claim.source_text == "Try this."
    with pytest.raises(VoiceError):
        await ledger.claim(op, kind="speech", fingerprint="b" * 64, reserve_usd=0.1)
    assert not await ledger.complete(
        op,
        claim.token,
        VoiceResult(
            audio_key=f"{uuid4().hex}.pcm",
            audio_bytes=2,
            sample_rate=24000,
            provider="test",
            model="test",
        ),
    )
    assert await ledger.complete(
        op,
        claim.token,
        VoiceResult(
            audio_key=claim.audio_key,
            audio_bytes=2,
            sample_rate=24000,
            provider="test",
            model="test",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["expired", "deleted"])
async def test_lazy_retention_releases_transcript_memory_and_preserves_live_receipts(cause):
    import weakref
    from dataclasses import replace
    from datetime import timedelta

    now = datetime.now(UTC)
    sessions = MemorySessionStore()
    sessions.save(session())
    ledger = MemoryVoiceLedger(sessions, clock=lambda: now)
    op = operation()
    admitted = await ledger.claim(op, kind="transcription", fingerprint="a" * 64, reserve_usd=0.1)
    result = VoiceResult(text="Private learner answer", provider="test", model="test")
    reference = weakref.ref(result)
    assert await ledger.complete(op, admitted.token, result)
    del result
    assert reference() is not None
    if cause == "deleted":
        sessions.delete("s")
    else:
        now += timedelta(days=1)
    sessions.save(session().model_copy(update={"session_id": "other", "started_at": now}))
    await ledger.claim(
        replace(op, session_id="other", operation_id=uuid4()),
        kind="transcription",
        fingerprint="a" * 64,
        reserve_usd=0.1,
    )
    assert reference() is None


def test_persisted_transcript_cannot_be_empty():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VoiceResult(text="", provider="test", model="test")
