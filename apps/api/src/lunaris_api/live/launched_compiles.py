import asyncio
from collections import OrderedDict

from lunaris_live.graph import ConceptGraph

#: How many failed compiles the process keeps the reason for. Failures are the rare case and a
#: session reads its own once, so this is a backstop against a long-lived process remembering every
#: bad topic ever tried, not a working set.
_MAX_FAILURES = 256


class LaunchedCompiles:
    """What this process knows about the compiles ``LiveGraphService.launch`` started and walked
    away from, by graph id, so a session that opened on one can ask how it ended (P2c T2).

    Process-wide, like the throttle, and for the same reason: the compile plane is built per
    request, so a registry held on an instance would be empty by the time the next request asked.
    In-process only: a compile that ran in another process is unknown here, and the session plane
    has its own deadline fallback for that.

    Holds a task only while it runs. When it ends, the task is let go either way — a finished
    compile retains the whole map it produced, and holding that for the life of the process is a
    leak (found in review) — and only a *failure* leaves anything behind: its reason, in a bounded
    store, readable as often as a session needs to (a poll that reads it and cannot yet act on it
    must not have consumed it, also found in review). A success leaves nothing: the map is in the
    store, and the store is the record.
    """

    def __init__(self) -> None:
        self._running: dict[str, asyncio.Task[ConceptGraph]] = {}
        self._failed: OrderedDict[str, str] = OrderedDict()

    def remember(self, graph_id: str, compiling: "asyncio.Task[ConceptGraph]") -> None:
        self._running[graph_id] = compiling
        compiling.add_done_callback(lambda task: self._settle(graph_id, task))

    def compiling(self, graph_id: str) -> "asyncio.Task[ConceptGraph] | None":
        """The compile still running for ``graph_id`` here, if any — the thing to await when a
        caller wants to meet it at its end rather than guess when that is."""
        return self._running.get(graph_id)

    def failure_of(self, graph_id: str) -> str | None:
        """Why the compile for ``graph_id`` failed, or ``None``.

        ``None`` is three things and the caller must not tell them apart here: still running,
        succeeded, or launched somewhere this process cannot see. Only a failure is knowledge worth
        having on this side — it is what lets a placing session stop interviewing for a map that
        will never come. Reading does not consume it: the session that acts on it says so with
        ``forget``, once it has persisted the close.
        """
        return self._failed.get(graph_id)

    def forget(self, graph_id: str) -> None:
        """The failure has been acted on (the session that owned it closed and said so)."""
        self._failed.pop(graph_id, None)

    def _settle(self, graph_id: str, task: "asyncio.Task[ConceptGraph]") -> None:
        # Guarded: a later launch under the same id (a retry) may have replaced the entry.
        if self._running.get(graph_id) is task:
            del self._running[graph_id]
        if task.cancelled():
            reason: str | None = "The compile was cancelled."
        else:
            error = task.exception()
            reason = None if error is None else (str(error) or "The compile failed.")
        if reason is None:
            return
        self._failed[graph_id] = reason
        while len(self._failed) > _MAX_FAILURES:
            self._failed.popitem(last=False)
