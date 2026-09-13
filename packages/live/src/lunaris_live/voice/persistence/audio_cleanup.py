from asyncio import to_thread

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from ..protocols.audio_store import IVoiceAudioStore


class VoiceAudioCleanup:
    """Bounded maintenance: delete via Storage first, acknowledge tombstones only afterward."""

    def __init__(self, audio: IVoiceAudioStore, *, client: object | None = None) -> None:
        self._audio, self._client = audio, client

    @guard("live voice retention")
    def _rpc(self, name: str, params: dict[str, object]) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env="SUPABASE_URL",
                service_key_env="SUPABASE_SERVICE_ROLE_KEY",
                purpose="clean generated voice audio",
            )
        return self._client.rpc(name, params).execute().data  # type: ignore[attr-defined]

    async def run_once(self) -> int:
        rows = await to_thread(self._rpc, "due_live_voice_audio_cleanup", {})
        count = 0
        for row in rows:  # type: ignore[union-attr]
            key = row["object_key"]
            await self._audio.delete(key)
            await to_thread(self._rpc, "ack_live_voice_audio_cleanup", {"p_key": key})
            count += 1
        return count
