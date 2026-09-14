import anyio
import structlog
from fastapi.responses import StreamingResponse
from starlette.types import Send


class VoiceStreamingResponse(StreamingResponse):
    """Close the producer when ASGI send fails between yielded chunks, preserving task context."""

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                with anyio.move_on_after(8, shield=True) as cleanup:
                    await close()
                if cleanup.cancel_called:
                    structlog.get_logger().warning("live.voice.stream_cleanup_timed_out")
