from uuid import uuid4

import httpx
import pytest
from lunaris_live.voice.persistence.memory_audio_store import MemoryVoiceAudioStore
from lunaris_live.voice.persistence.supabase_audio_store import SupabaseVoiceAudioStore


@pytest.mark.asyncio
async def test_generated_pcm_is_private_immutable_and_removed_through_storage_api():
    objects = {}
    seen = []
    key = f"{uuid4().hex}.pcm"

    def serve(request):
        seen.append((request.method, request.url.path))
        assert request.headers["authorization"] == "Bearer server-secret"
        if request.method == "POST":
            assert request.headers.get("x-upsert") == "false"
            objects[key] = request.content
            return httpx.Response(200, json={"Key": key})
        if request.method == "GET":
            return httpx.Response(200, content=objects[key])
        objects.clear()
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        store = SupabaseVoiceAudioStore(
            url="https://storage.example", key="server-secret", client=client
        )
        await store.put(key, b"\x00\x01")
        assert await store.get(key) == b"\x00\x01"
        await store.delete(key)
    assert not objects
    assert seen == [
        ("POST", f"/storage/v1/object/live-voice/{key}"),
        ("GET", f"/storage/v1/object/authenticated/live-voice/{key}"),
        ("DELETE", "/storage/v1/object/live-voice"),
    ]


@pytest.mark.asyncio
async def test_memory_pcm_rejects_overwrite_invalid_samples_and_paths():
    store = MemoryVoiceAudioStore()
    key = f"{uuid4().hex}.pcm"
    await store.put(key, b"\0\0")
    with pytest.raises(FileExistsError):
        await store.put(key, b"\1\1")
    with pytest.raises(ValueError):
        await store.put(key, b"\0")
    with pytest.raises(ValueError):
        await store.get("../other")
    await store.delete(key)
    with pytest.raises(FileNotFoundError):
        await store.get(key)


@pytest.mark.asyncio
async def test_cleanup_failure_keeps_tombstone_for_retry():
    from lunaris_live.voice.persistence.audio_cleanup import VoiceAudioCleanup

    key = f"{uuid4().hex}.pcm"
    acknowledged = []

    class Response:
        def __init__(self):
            self.data = [{"object_key": key}]

        def execute(self):
            return self

    class Database:
        def rpc(self, name, params):
            if name == "ack_live_voice_audio_cleanup":
                acknowledged.append(params["p_key"])
            return Response()

    class Audio:
        fails = True

        async def delete(self, key):
            if self.fails:
                raise RuntimeError("storage unavailable")

    audio = Audio()
    cleanup = VoiceAudioCleanup(audio, client=Database())
    with pytest.raises(RuntimeError):
        await cleanup.run_once()
    assert not acknowledged
    audio.fails = False
    assert await cleanup.run_once() == 1
    assert acknowledged == [key]


@pytest.mark.asyncio
async def test_memory_generated_audio_expires_after_replay_retention():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    store = MemoryVoiceAudioStore(clock=lambda: now)
    key = f"{uuid4().hex}.pcm"
    await store.put(key, b"\0\0")
    now += timedelta(days=1)
    with pytest.raises(FileNotFoundError):
        await store.get(key)
