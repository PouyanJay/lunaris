from typing import Protocol

from ..config_store import KNOWN_CONFIG

# The non-secret config a tenant owns per build: model selection. Maps the web/API config id to the
# environment variable the runtime reads (a subset of KNOWN_CONFIG — LangSmith tracing/project are
# operator-only deploy config, not per-tenant). Must stay in lockstep with the config_key CHECK in
# the user_runtime_config migration: a new per-user key is a change in both places.
PER_USER_CONFIG: dict[str, str] = {
    "modelStrong": KNOWN_CONFIG["modelStrong"],
    "modelWorker": KNOWN_CONFIG["modelWorker"],
}


class IUserConfigStore(Protocol):
    """Per-user storage for non-secret runtime config (model selection).

    Every method is scoped to a ``user_id`` (the authenticated owner), so one tenant can neither
    read nor write another's config. Concrete backends: an in-memory fallback (no-DB/CI) and the
    Supabase-backed store (production, owner-scoped RLS). The store holds only the raw key→value the
    user set; defaults + rendering metadata live in ``config_store`` and are applied by the service.

    Contract: ``get_all`` returns only the keys the user has explicitly set (others absent → the
    caller applies the default); ``set`` upserts one value per key per user (re-setting overwrites).
    """

    async def get_all(self, *, user_id: str) -> dict[str, str]: ...

    async def set(self, *, user_id: str, key: str, value: str) -> None: ...
