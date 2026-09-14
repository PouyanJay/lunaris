from collections.abc import AsyncGenerator, Awaitable, Callable


class SpeechStream:
    """Explicit close also settles an admitted stream that never began iteration."""

    def __init__(
        self, iterator: AsyncGenerator[bytes, None], unstarted_close: Callable[[], Awaitable[None]]
    ) -> None:
        self._iterator = iterator
        self._unstarted_close = unstarted_close
        self._started = False
        self._closed = False

    def __aiter__(self) -> "SpeechStream":
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        self._started = True
        try:
            return await anext(self._iterator)
        except BaseException:
            self._closed = True
            raise

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started:
            await self._iterator.aclose()
        else:
            await self._unstarted_close()
