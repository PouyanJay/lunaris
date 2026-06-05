import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

# Logical secret id (the web/API contract) → the environment variable the runtime reads.
# The harness/adapters already read these env vars, so populating os.environ is how a
# UI-provided key reaches Claude/Voyage/Supabase without threading it through every call site.
KNOWN_SECRETS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "voyage": "EMBEDDINGS_API_KEY",
    "supabaseUrl": "SUPABASE_URL",
    "supabaseServiceRole": "SUPABASE_SERVICE_ROLE_KEY",
    "search": "SEARCH_API_KEY",
    "youtube": "YOUTUBE_API_KEY",
    "langsmith": "LANGSMITH_API_KEY",
}


@dataclass(frozen=True)
class SecretStatus:
    """The only thing the API ever reveals about a stored secret — never the value."""

    name: str
    is_set: bool
    last4: str | None


class SecretStore:
    """A write-only secret store for operator-provided keys (local-dev secret manager).

    Secrets enter from the Settings UI and are (a) persisted to a gitignored, owner-only
    (0600) JSON file so they survive restarts, and (b) applied to ``os.environ`` so the
    existing runtime adapters pick them up. The value is never returned by the API: callers
    get only ``SecretStatus`` (set/unset + last4). ``reveal`` exists for backend-internal use
    only (never wire it to a route). No value is ever logged.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._values: dict[str, str] = self._load()
        self._apply_to_env()

    def set(self, name: str, value: str) -> SecretStatus:
        self._require_known(name)
        self._values[name] = value
        self._persist()
        os.environ[KNOWN_SECRETS[name]] = value
        return self._status(name)

    def clear(self, name: str) -> SecretStatus:
        self._require_known(name)
        self._values.pop(name, None)
        self._persist()
        os.environ.pop(KNOWN_SECRETS[name], None)
        return self._status(name)

    def reveal(self, name: str) -> str | None:
        """Backend-internal only — return the raw value. NEVER expose this over the API."""
        return self._values.get(name)

    def statuses(self) -> list[SecretStatus]:
        return [self._status(name) for name in KNOWN_SECRETS]

    # --- internals ----------------------------------------------------------

    def _status(self, name: str) -> SecretStatus:
        value = self._values.get(name)
        last4 = value[-4:] if value and len(value) >= 4 else None
        return SecretStatus(name=name, is_set=bool(value), last4=last4)

    def _require_known(self, name: str) -> None:
        if name not in KNOWN_SECRETS:
            raise KeyError(name)

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text())
        return {k: str(v) for k, v in data.items() if k in KNOWN_SECRETS}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._values, indent=2))
        self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — owner read/write only

    def _apply_to_env(self) -> None:
        for name, value in self._values.items():
            os.environ[KNOWN_SECRETS[name]] = value
