import os
import stat
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, set_key, unset_key

# Logical secret id (the web/API contract) → the environment variable the runtime reads.
# The harness/adapters already read these env vars, so populating os.environ + the .env file is
# how a UI-provided key reaches Claude/Voyage/Supabase without threading it through every call site.
KNOWN_SECRETS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "voyage": "EMBEDDINGS_API_KEY",
    "supabaseUrl": "SUPABASE_URL",
    "supabaseServiceRole": "SUPABASE_SERVICE_ROLE_KEY",
    "search": "SEARCH_API_KEY",
    "youtube": "YOUTUBE_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "openai": "OPENAI_API_KEY",  # AI course covers (GPT Image 2) — course-cover-images
    "langsmith": "LANGSMITH_API_KEY",
}

_OWNER_RW_ONLY = stat.S_IRUSR | stat.S_IWUSR  # 0600 — owner read/write only


def contains_control_characters(value: str) -> bool:
    """A newline/CR in a secret value could inject extra ``KEY=value`` lines into the ``.env`` file
    or break its parser; NUL can truncate it on some platforms — hence reject all control chars."""
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)


@dataclass(frozen=True)
class SecretStatus:
    """The only thing the API ever reveals about a stored secret — never the value."""

    name: str
    is_set: bool
    last4: str | None


class SecretStore:
    """A write-only secret store for operator-provided keys, backed by the ``.env`` file.

    Secrets enter from the Settings UI and are (a) upserted into the gitignored ``.env`` file — the
    single source of truth, loaded at process startup via ``uv run --env-file .env`` — and (b)
    applied to ``os.environ`` so the running process picks them up without a restart. The value is
    never returned by the API: callers get only ``SecretStatus`` (set/unset + last4). ``reveal``
    exists for backend-internal use only (never wire it to a route). No value is ever logged.

    Security posture: the ``.env`` file is forced to 0600 (owner-only) after every write — note
    ``set_key`` preserves a file's *existing* mode, so a pre-existing 0644 ``.env`` would otherwise
    stay world-readable. Control characters are rejected (``.env`` line-injection). Writes are
    atomic: ``python-dotenv`` rewrites via a temp file in the same directory + ``os.replace``.
    Reads are file-fresh, so a manually edited ``.env`` value surfaces and no stale in-memory cache
    competes with ``--env-file``.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._apply_to_env()

    def set(self, name: str, value: str) -> SecretStatus:
        self._require_known(name)
        if not value:
            raise ValueError("Secret value must not be empty.")
        if contains_control_characters(value):
            raise ValueError("Secret value must not contain control characters.")
        var = KNOWN_SECRETS[name]
        # set_key needs the parent dir to exist (it writes a sibling temp file); the repo-root
        # default always does, but a custom LUNARIS_ENV_FILE path may not.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        set_key(str(self._path), var, value, quote_mode="auto")
        # set_key rewrites via temp+os.replace but preserves the file's existing mode, so tighten
        # to owner-only after every write or a pre-existing 0644 .env would stay world-readable.
        self._enforce_owner_only()
        os.environ[var] = value
        return self._status(name, value)

    def clear(self, name: str) -> SecretStatus:
        self._require_known(name)
        var = KNOWN_SECRETS[name]
        if self._path.exists():
            unset_key(str(self._path), var)
            self._enforce_owner_only()
        os.environ.pop(var, None)
        return self._status(name, None)

    def reveal(self, name: str) -> str | None:
        """Backend-internal only — return the raw value. NEVER expose this over the API."""
        var = KNOWN_SECRETS.get(name)
        return self._file_values().get(var) if var else None

    def statuses(self) -> list[SecretStatus]:
        values = self._file_values()
        return [self._status(name, values.get(KNOWN_SECRETS[name])) for name in KNOWN_SECRETS]

    # --- internals ----------------------------------------------------------

    def _status(self, name: str, value: str | None) -> SecretStatus:
        last4 = value[-4:] if value and len(value) >= 4 else None
        return SecretStatus(name=name, is_set=bool(value), last4=last4)

    def _require_known(self, name: str) -> None:
        if name not in KNOWN_SECRETS:
            raise KeyError(name)

    def _file_values(self) -> dict[str, str]:
        """The KNOWN_SECRETS env vars currently set in the ``.env`` file (blank values dropped)."""
        if not self._path.exists():
            return {}
        known = set(KNOWN_SECRETS.values())
        return {k: v for k, v in dotenv_values(self._path).items() if k in known and v}

    def _apply_to_env(self) -> None:
        for var, value in self._file_values().items():
            os.environ[var] = value

    def _enforce_owner_only(self) -> None:
        if self._path.exists():
            self._path.chmod(_OWNER_RW_ONLY)
