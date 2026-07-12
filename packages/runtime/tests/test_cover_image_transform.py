"""A cover's signed URL can carry a server-side resize (Supabase Storage image transformations).

Covers are 2048x1152 masters — multi-megabyte PNGs. Handing that master to a 260px card and letting
the browser shrink it is what makes a card cover look soft, so the display surfaces ask storage for
an already-resized derivative instead. These tests pin the seam: the transform reaches the storage
backend, and an untransformed request stays exactly as it was (the lightbox still gets the master).
"""

import pytest
from lunaris_runtime.persistence import (
    CoverImageTransform,
    InMemoryCoverStorage,
    SupabaseCoverStorage,
)

_PATH = "user-1/course-1/job-1/cover.png"
_CARD = CoverImageTransform(width=1280, height=720)


class _FakeBucket:
    """Records what supabase-py's ``create_signed_url`` was actually called with."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, object]] = []

    def create_signed_url(self, path: str, expires_in: int, options: object = None) -> dict:
        self.calls.append((path, expires_in, options))
        return {"signedURL": f"https://signed/{path}"}


class _FakeStorageNamespace:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def from_(self, _bucket_id: str) -> _FakeBucket:
        return self._bucket


class _FakeSupabaseClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self.storage = _FakeStorageNamespace(bucket)


async def test_supabase_signs_the_transform_into_the_url() -> None:
    # The resize must be SIGNED into the URL, not appended by the caller: storage-api reads the
    # transformation from the token payload and ignores query params on a signed URL.
    bucket = _FakeBucket()
    storage = SupabaseCoverStorage(client=_FakeSupabaseClient(bucket))

    await storage.signed_url(path=_PATH, transform=_CARD)

    (_path, _expires, options) = bucket.calls[0]
    assert options == {
        "transform": {"width": 1280, "height": 720, "quality": 90, "resize": "cover"}
    }


async def test_supabase_omits_options_when_no_transform_is_asked_for() -> None:
    # The lightbox wants the untouched master — an untransformed mint must not start sending a
    # transform payload, which would silently downscale the full-size view.
    bucket = _FakeBucket()
    storage = SupabaseCoverStorage(client=_FakeSupabaseClient(bucket))

    await storage.signed_url(path=_PATH)

    (_path, _expires, options) = bucket.calls[0]
    assert options is None


@pytest.mark.parametrize("transform", [None, _CARD])
async def test_memory_double_distinguishes_the_derivative_from_the_master(
    transform: CoverImageTransform | None,
) -> None:
    # The double's pseudo-URL must differ per transform, or a test could not tell a card derivative
    # from the master it was resized from.
    storage = InMemoryCoverStorage()

    url = await storage.signed_url(path=_PATH, transform=transform)

    assert (_PATH in url) is True
    assert ("width=1280" in url) is (transform is not None)


async def test_resize_mode_matches_the_css_object_fit() -> None:
    # The frames crop with CSS ``object-fit: cover``; the server-side resize must crop the same way,
    # or the derivative and the master would frame the artwork differently.
    assert CoverImageTransform(width=1, height=1).resize == "cover"
