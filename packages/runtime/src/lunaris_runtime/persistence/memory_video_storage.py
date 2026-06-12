class InMemoryVideoStorage:
    """The in-memory storage double: byte-for-byte upload semantics, no Supabase.

    Serves tests and the keyless/local path. ``signed_url`` returns a deterministic
    pseudo-URL that embeds the path, which is all the API/web layers need to thread it
    through. The extra read accessors (``paths``/``read``/``content_type``) exist for test
    assertions — production code only sees the ``IVideoStorage`` surface.
    """

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None:
        self._objects[path] = (data, content_type)  # upsert, like the real bucket

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        return f"memory://course-videos/{path}?signed=true"

    def paths(self) -> list[str]:
        return list(self._objects)

    def read(self, path: str) -> bytes:
        return self._objects[path][0]

    def content_type(self, path: str) -> str:
        return self._objects[path][1]
