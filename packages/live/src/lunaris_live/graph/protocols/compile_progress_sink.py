from typing import Protocol

from ..schema import CompileProgress


class ICompileProgressSink(Protocol):
    """Where a compile reports its progress to.

    Called from inside the compile's own task, so it must return promptly and must not await —
    handing a beat to a queue is the intended shape, doing work in here is not. It is also allowed
    to fail: a client that disconnects mid-compile is ordinary, and the compiler treats a raising
    sink as telemetry lost rather than as the compile failing.
    """

    def __call__(self, progress: CompileProgress) -> None: ...
