import asyncio

from fastapi import Request
from lunaris_live.voice.error import VoiceError


async def read_voice_recording(request: Request, *, timeout_s: float = 15) -> bytes:
    """Bound the upload before buffering or admitting any provider work."""
    data = bytearray()
    try:
        async with asyncio.timeout(timeout_s):
            async for chunk in request.stream():
                if len(data) + len(chunk) > 1_920_044:
                    raise VoiceError("Recording exceeds the 60-second limit.", status_code=413)
                data.extend(chunk)
    except TimeoutError as exc:
        raise VoiceError(
            "Recording upload timed out. Try again or type your answer.", status_code=408
        ) from exc
    return bytes(data)
