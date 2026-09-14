import asyncio

import pytest
from lunaris_api.live.voice.recording_body import read_voice_recording
from lunaris_live.voice.error import VoiceError


async def test_upload_timeout_refuses_a_stalled_request_before_paid_admission():
    class Body:
        async def stream(self):
            yield b"RIFF"
            await asyncio.Event().wait()

    with pytest.raises(VoiceError) as caught:
        await read_voice_recording(Body(), timeout_s=0.001)
    assert caught.value.status_code == 408


async def test_oversized_chunk_is_rejected_before_buffering():
    class Body:
        async def stream(self):
            yield b"x" * 1_920_045

    with pytest.raises(VoiceError) as caught:
        await read_voice_recording(Body())
    assert caught.value.status_code == 413
