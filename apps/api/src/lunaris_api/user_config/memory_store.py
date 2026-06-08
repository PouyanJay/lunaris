class InMemoryUserConfigStore:
    """In-process per-user config store — the no-DB/CI fallback and test stub.

    Values live only for the process lifetime (lost on restart); durable storage requires the
    Supabase-backed store. Entries are keyed by ``(user_id, key)`` so isolation is structural — a
    read for one user can never reach another's value.
    """

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    async def get_all(self, *, user_id: str) -> dict[str, str]:
        return {key: value for (uid, key), value in self._values.items() if uid == user_id}

    async def set(self, *, user_id: str, key: str, value: str) -> None:
        self._values[(user_id, key)] = value
