from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .validate_pcm import validate_pcm


class MemoryVoiceAudioStore:
    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._audio: dict[str, tuple[datetime, bytes]] = {}
        self._clock = clock

    def _expire(self) -> None:
        now = self._clock()
        self._audio = {key: item for key, item in self._audio.items() if item[0] > now}

    async def put(self, key: str, pcm: bytes) -> None:
        validate_pcm(key, pcm)
        self._expire()
        if key in self._audio:
            raise FileExistsError(key)
        self._audio[key] = (self._clock() + timedelta(days=1), pcm)

    async def get(self, key: str) -> bytes:
        validate_pcm(key)
        self._expire()
        if key not in self._audio:
            raise FileNotFoundError(key)
        return self._audio[key][1]

    async def delete(self, key: str) -> None:
        validate_pcm(key)
        self._audio.pop(key, None)
