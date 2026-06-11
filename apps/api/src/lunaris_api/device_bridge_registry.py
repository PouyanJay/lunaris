"""The process-wide registry of in-flight device bridges, keyed by ``run_id``.

The build request creates a run's bridge and the tab's bridge-router requests must find the SAME
instance, so the registry is a composition-root singleton (the ``RunRegistry`` pattern). Entries
are owner-scoped: when auth is on, only the run's owner can poll or answer its completions.
"""

from lunaris_runtime.device_bridge import DeviceBridge


class DeviceBridgeRegistry:
    """In-flight device bridges by run_id, with owner-scoped lookup."""

    def __init__(self) -> None:
        self._bridges: dict[str, DeviceBridge] = {}
        # The owner per bridge, mirroring RunRegistry: None = unscoped (auth off / single-user).
        self._owners: dict[str, str | None] = {}

    def register(self, run_id: str, bridge: DeviceBridge, owner_id: str | None = None) -> None:
        self._bridges[run_id] = bridge
        self._owners[run_id] = owner_id

    def lookup(self, run_id: str, owner_id: str | None = None) -> DeviceBridge | None:
        """The run's bridge, or ``None`` when unknown — or owned by someone else, which must read
        the same as unknown (a 404, never an existence leak). A ``None`` caller (auth off) is
        unscoped, preserving single-user behaviour."""
        bridge = self._bridges.get(run_id)
        if bridge is None:
            return None
        if owner_id is not None and self._owners.get(run_id) != owner_id:
            return None
        return bridge

    def discard(self, run_id: str) -> None:
        """Forget a finished run's bridge (called from the build's teardown). Idempotent."""
        self._bridges.pop(run_id, None)
        self._owners.pop(run_id, None)
