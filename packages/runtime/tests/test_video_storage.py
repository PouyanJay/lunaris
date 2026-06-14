"""Video-storage tests: the in-memory double's behavior, the Supabase store's call construction
against a fake client, and the artifact path convention both the worker and the API key off."""

from typing import Any

import pytest
from lunaris_runtime.persistence import (
    InMemoryVideoStorage,
    PersistenceError,
    SupabaseVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import VideoJob, VideoKind


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


def test_artifact_paths_follow_the_owner_prefix_convention() -> None:
    # Act
    paths = VideoArtifactPaths.for_job(_job())

    # Assert — {user_id}/{course_id}/{job_id}/… is the storage-policy and prefix-delete contract;
    # every artifact (playable + regeneration) shares the one job prefix.
    prefix = "00000000-0000-0000-0000-000000000001/course-1/job-1"
    assert paths.mp4 == f"{prefix}/final.mp4"
    assert paths.poster == f"{prefix}/poster.jpg"
    assert paths.contracts == f"{prefix}/scene_contracts.json"
    assert paths.timing == f"{prefix}/timing.json"
    assert paths.provenance == f"{prefix}/provenance.json"


# ── in-memory double ──────────────────────────────────────────────────────────────


async def test_upload_then_read_roundtrip() -> None:
    # Arrange
    storage = InMemoryVideoStorage()

    # Act
    await storage.upload(path="u/c/j/final.mp4", data=b"bytes", content_type="video/mp4")

    # Assert
    assert storage.read("u/c/j/final.mp4") == b"bytes"
    assert storage.content_type("u/c/j/final.mp4") == "video/mp4"
    assert storage.paths() == ["u/c/j/final.mp4"]


async def test_upload_overwrites_in_place() -> None:
    # Arrange
    storage = InMemoryVideoStorage()
    await storage.upload(path="p", data=b"old", content_type="video/mp4")

    # Act — a regenerate writes over the same path.
    await storage.upload(path="p", data=b"new", content_type="video/mp4")

    # Assert — replaced in place, not appended.
    assert storage.read("p") == b"new"
    assert len(storage.paths()) == 1


async def test_download_returns_the_uploaded_bytes() -> None:
    # Arrange — the API downloads small JSON artifacts (provenance) to thread onto the wire.
    storage = InMemoryVideoStorage()
    await storage.upload(path="u/c/j/provenance.json", data=b'{"jobId":"j"}', content_type="json")

    # Act / Assert
    assert await storage.download(path="u/c/j/provenance.json") == b'{"jobId":"j"}'


async def test_download_of_a_missing_object_raises() -> None:
    # Arrange — a job rendered before V2 has no provenance.json; the API must degrade, not crash.
    storage = InMemoryVideoStorage()

    # Act / Assert
    with pytest.raises(PersistenceError):
        await storage.download(path="u/c/j/missing.json")


async def test_signed_url_is_deterministic_and_path_scoped() -> None:
    # Arrange
    storage = InMemoryVideoStorage()
    await storage.upload(path="u/c/j/final.mp4", data=b"x", content_type="video/mp4")

    # Act
    url = await storage.signed_url(path="u/c/j/final.mp4")

    # Assert — enough for the API/web layers to thread it through.
    assert "u/c/j/final.mp4" in url


async def test_delete_removes_given_paths_and_ignores_missing() -> None:
    # Arrange — the course-deletion cascade (V7-T4) deletes a job's full artifact set, some of which
    # a FAILED job never wrote — so delete must be idempotent over absent paths.
    storage = InMemoryVideoStorage()
    await storage.upload(path="u/c/j/final.mp4", data=b"x", content_type="video/mp4")
    await storage.upload(path="u/c/j/poster.jpg", data=b"y", content_type="image/jpeg")

    # Act — delete both real paths plus one that was never written.
    await storage.delete(paths=["u/c/j/final.mp4", "u/c/j/poster.jpg", "u/c/j/captions.vtt"])

    # Assert — the two real objects are gone; the missing one was a silent no-op.
    assert storage.paths() == []


# ── Supabase store: call construction against a fake client ──────────────────────


class _FakeBucket:
    def __init__(self, sink: list[dict[str, Any]], signed_response: dict[str, str]) -> None:
        self._sink = sink
        self._signed_response = signed_response

    def upload(self, path: str, data: bytes, file_options: dict[str, str]) -> None:
        self._sink.append(
            {"op": "upload", "path": path, "data": data, "file_options": file_options}
        )

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        self._sink.append({"op": "signed_url", "path": path, "expires_in": expires_in})
        return self._signed_response

    def download(self, path: str) -> bytes:
        self._sink.append({"op": "download", "path": path})
        return b'{"jobId":"j"}'

    def remove(self, paths: list[str]) -> list[dict[str, str]]:
        self._sink.append({"op": "remove", "paths": paths})
        return [{"name": p} for p in paths]


class _FakeStorageClient:
    def __init__(self, signed_response: dict[str, str]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.buckets: list[str] = []
        self._signed_response = signed_response

    def from_(self, bucket: str) -> _FakeBucket:
        self.buckets.append(bucket)
        return _FakeBucket(self.calls, self._signed_response)


class _FakeClient:
    def __init__(self, signed_response: dict[str, str] | None = None) -> None:
        default = {"signedURL": "https://signed.example/u/c/j/final.mp4?token=t"}
        self.storage = _FakeStorageClient(
            signed_response if signed_response is not None else default
        )


async def test_upload_targets_the_course_videos_bucket() -> None:
    # Arrange
    client = _FakeClient()
    storage = SupabaseVideoStorage(client=client)

    # Act
    await storage.upload(path="u/c/j/final.mp4", data=b"bytes", content_type="video/mp4")

    # Assert — upsert so a regenerate overwrites the same path instead of 409-ing.
    assert client.storage.buckets == ["course-videos"]
    call = client.storage.calls[0]
    assert call["op"] == "upload"
    assert call["path"] == "u/c/j/final.mp4"
    assert call["file_options"]["content-type"] == "video/mp4"
    assert call["file_options"]["upsert"] == "true"


async def test_download_targets_the_course_videos_bucket() -> None:
    # Arrange
    client = _FakeClient()
    storage = SupabaseVideoStorage(client=client)

    # Act
    data = await storage.download(path="u/c/j/provenance.json")

    # Assert — reads the provenance artifact straight off the private bucket.
    assert data == b'{"jobId":"j"}'
    assert client.storage.buckets == ["course-videos"]
    assert client.storage.calls[0] == {"op": "download", "path": "u/c/j/provenance.json"}


async def test_signed_url_unwraps_the_response() -> None:
    # Arrange
    client = _FakeClient()
    storage = SupabaseVideoStorage(client=client)

    # Act
    url = await storage.signed_url(path="u/c/j/final.mp4", expires_in_seconds=600)

    # Assert
    assert url == "https://signed.example/u/c/j/final.mp4?token=t"
    assert client.storage.calls[0]["expires_in"] == 600


async def test_signed_url_accepts_the_other_key_spelling() -> None:
    # Arrange — supabase-py has shipped both spellings across versions.
    client = _FakeClient(signed_response={"signedUrl": "https://signed.example/p?token=t"})
    storage = SupabaseVideoStorage(client=client)

    # Act / Assert
    assert await storage.signed_url(path="p") == "https://signed.example/p?token=t"


async def test_signed_url_with_no_url_in_the_response_raises() -> None:
    # Arrange — an empty response must surface, never hand the player a blank URL.
    client = _FakeClient(signed_response={})
    storage = SupabaseVideoStorage(client=client)

    # Act / Assert
    with pytest.raises(PersistenceError):
        await storage.signed_url(path="p")


async def test_delete_removes_paths_from_the_course_videos_bucket() -> None:
    # Arrange
    client = _FakeClient()
    storage = SupabaseVideoStorage(client=client)

    # Act
    await storage.delete(paths=["u/c/j/final.mp4", "u/c/j/poster.jpg"])

    # Assert — one batched remove() on the private bucket (storage.objects rejects SQL deletes).
    assert client.storage.buckets == ["course-videos"]
    assert client.storage.calls[0] == {
        "op": "remove",
        "paths": ["u/c/j/final.mp4", "u/c/j/poster.jpg"],
    }


async def test_delete_of_an_empty_batch_does_not_round_trip() -> None:
    # Arrange — a course with no video jobs cascades an empty path list; don't call the bucket.
    client = _FakeClient()
    storage = SupabaseVideoStorage(client=client)

    # Act
    await storage.delete(paths=[])

    # Assert
    assert client.storage.calls == []
