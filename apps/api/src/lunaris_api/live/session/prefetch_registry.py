import asyncio
from collections.abc import Coroutine


class PrefetchRegistry:
    """The material prefetches in flight in this process, and the tasks that carry them (P2c T4).

    Process-wide, wired from the composition root, like the throttle and the launched compiles: the
    session plane is built per request, and a prefetch started by one request must not be started
    again by the next while it is still running. Holds the task references too — a fire-and-forget
    task nothing references can be collected before it runs — and lets them go when they end. Tests
    meet the prefetches at their end with ``settled``.
    """

    def __init__(self) -> None:
        self._in_flight: dict[tuple[str | None, str, str], asyncio.Task[None]] = {}
        # Work that leads to a prefetch without being one (the map landing behind a placing
        # session): held here so ``settled`` covers it, and so nothing collects it before it runs.
        self._leading: set[asyncio.Task[None]] = set()

    def is_running(self, owner_id: str | None, graph_id: str, node_id: str) -> bool:
        return (owner_id, graph_id, node_id) in self._in_flight

    def start(
        self,
        owner_id: str | None,
        graph_id: str,
        node_id: str,
        work: Coroutine[object, object, None],
    ) -> "asyncio.Task[None] | None":
        """Run ``work`` as the prefetch of ``(owner, graph, node)``, unless one is already running,
        in which case ``work`` is closed unstarted and nothing happens."""
        key = (owner_id, graph_id, node_id)
        if key in self._in_flight:
            work.close()
            return None
        task = asyncio.create_task(work)
        self._in_flight[key] = task
        task.add_done_callback(lambda done: self._settle(key, done))
        return task

    def lead(self, work: Coroutine[object, object, None]) -> "asyncio.Task[None]":
        """Run ``work`` (something that will schedule a prefetch) as a task this registry holds."""
        task = asyncio.create_task(work)
        self._leading.add(task)
        task.add_done_callback(self._leading.discard)
        return task

    async def settled(self) -> None:
        """Wait for everything running now — the work leading to prefetches, and the prefetches —
        to end (a rendezvous for tests and shutdown)."""
        while self._leading or self._in_flight:
            await asyncio.gather(
                *list(self._leading), *list(self._in_flight.values()), return_exceptions=True
            )

    def _settle(self, key: tuple[str | None, str, str], task: "asyncio.Task[None]") -> None:
        if self._in_flight.get(key) is task:
            del self._in_flight[key]


_registry = PrefetchRegistry()


def prefetch_registry() -> PrefetchRegistry:
    """The process-wide registry (one per process, like the throttle); its class's one companion."""
    return _registry
