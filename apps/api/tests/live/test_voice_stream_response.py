"""ASGI send failures must close provider iterators in their original producer task."""

import asyncio

import pytest
from lunaris_api.live.voice.stream_response import VoiceStreamingResponse


async def test_broken_client_send_closes_voice_generator_in_producer_task():
    closed = []
    producer = asyncio.current_task()

    async def chunks():
        try:
            yield b"\x01\x00"
            await asyncio.Event().wait()
        finally:
            closed.append(asyncio.current_task())

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("client disconnected")

    with pytest.raises(OSError):
        await VoiceStreamingResponse(chunks()).stream_response(send)
    assert closed == [producer]
