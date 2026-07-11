from .persistence_error import PersistenceError


class InMemoryCoverStorage:
    """The in-memory cover-storage double: byte-for-byte upload semantics, no Supabase.

    Serves tests and the keyless/local path. ``signed_url`` returns a deterministic pseudo-URL that
    embeds the path, which is all the API/web layers need to thread it through. The extra read
    accessors (``paths``/``read``/``content_type``) exist for test assertions — production code only
    sees the ``ICoverStorage`` surface.
    """

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None:
        self._objects[path] = (data, content_type)  # upsert, like the real bucket

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        return f"memory://course-covers/{path}?signed=true"

    async def download(self, *, path: str) -> bytes:
        stored = self._objects.get(path)
        if stored is None:
            raise PersistenceError(f"no object at {path!r}")
        return stored[0]

    async def delete(self, *, paths: list[str]) -> None:
        for path in paths:
            self._objects.pop(path, None)  # idempotent, like the real bucket's remove()

    def paths(self) -> list[str]:
        return list(self._objects)

    def read(self, path: str) -> bytes:
        return self._objects[path][0]

    def content_type(self, path: str) -> str:
        return self._objects[path][1]
