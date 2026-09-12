from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import signature
from typing import Any, Literal


def coordinated(kind: Literal["session", "graph"], *, wait_s: float = 0) -> Callable:
    """Acquire before the method reads mutable state; nested lifecycle calls reuse its lease."""

    def decorate(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        parameters = signature(method)

        @wraps(method)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            bound = parameters.bind(self, *args, **kwargs)
            identity = bound.arguments["session_id" if kind == "session" else "graph_id"]
            scope = getattr(self._transactions, kind)
            options = {"wait_s": wait_s} if kind == "graph" else {}
            async with scope(identity, bound.arguments.get("owner_id"), **options):
                return await method(self, *args, **kwargs)

        return wrapped

    return decorate
