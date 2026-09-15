"""Ready owner-authorized Studio artifacts yield measured, aligned clip inventory."""

import json
import struct

import httpx
import pytest
from lunaris_api.live.corpus.video_inventory import StudioVideoInventory
from lunaris_api.live.corpus.video_media import SignedVideoMedia
from lunaris_runtime.persistence.memory_video_job_queue import InMemoryVideoJobQueue
from lunaris_runtime.persistence.memory_video_storage import InMemoryVideoStorage
from lunaris_runtime.persistence.video_artifact_paths import VideoArtifactPaths
from lunaris_runtime.schema import Course, VideoJob
from lunaris_runtime.video_build.input_hash import lesson_video_input_hash
from lunaris_video.hashing.contract_hash import contract_hash
from lunaris_video.schemas import SceneContracts, TimingManifest
from lunaris_video.style import video_global_style


def mp4() -> bytes:
    def box(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I4s", len(data) + 8, kind) + data

    mvhd = bytes(12) + struct.pack(">II", 1000, 2700) + bytes(80)
    hdlr = bytes(8) + b"vide" + bytes(12)
    return box(b"ftyp", b"isom" + bytes(4)) + box(
        b"moov", box(b"mvhd", mvhd) + box(b"trak", box(b"mdia", box(b"hdlr", hdlr)))
    )


class Courses:
    def __init__(self) -> None:
        self.course = Course.model_validate(
            {
                "id": "course1",
                "topic": "Records",
                "status": "published",
                "modules": [
                    {
                        "id": "m1",
                        "title": "Records",
                        "lessons": [
                            {
                                "id": "lesson1",
                                "segments": {
                                    key: {"prose": "Records store data"}
                                    for key in ("activate", "demonstrate", "apply", "integrate")
                                },
                            }
                        ],
                    }
                ],
            }
        )

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        if course_id != "course1" or owner_id != "owner1":
            raise FileNotFoundError(course_id)
        return self.course


class SignedStorage(InMemoryVideoStorage):
    def __init__(self) -> None:
        super().__init__()
        self.reads: list[str] = []

    async def download(self, *, path: str) -> bytes:
        self.reads.append(path)
        return await super().download(path=path)

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        return "https://storage.test/" + path + "?token=private"


async def fixture(
    status: str = "ready", silent: bool = False, degraded: bool = False
) -> tuple[InMemoryVideoJobQueue, SignedStorage]:
    queue, storage = InMemoryVideoJobQueue(), SignedStorage()
    contracts = SceneContracts.model_validate(
        {
            "topic": "Records",
            "audience": "beginner",
            "visual_archetypes_used": ["number_line"],
            "asset_strategy": "procedural",
            "global_style": video_global_style(),
            "scenes": [
                {
                    "id": "S1_records",
                    "archetype": "number_line",
                    "narration": "Records store data.",
                    "objects": ["record"],
                    "beats": [{"id": "b1", "action": "draw", "narration": "Records store data."}],
                    "sources": ["framing"],
                    "duration_s": 2,
                }
            ],
        }
    )
    timing = TimingManifest.model_validate(
        {
            "S1_records": {
                "beats": [
                    {
                        "id": "b1",
                        "audio_s": 2,
                        "anim_s": 2,
                        "audio": None if silent else "voice.mp3",
                        "estimated": silent,
                    }
                ],
                "total_s": 2,
            }
        }
    )
    job = VideoJob(
        id="job1",
        user_id="owner1",
        course_id="course1",
        kind="lesson",
        lesson_id="lesson1",
        config={"target_seconds": 90},
        status=status,
        input_hash=lesson_video_input_hash(
            "course1", Courses().course.modules[0].lessons[0], target_seconds=90
        ),
        contract_hash=contract_hash(contracts),
    )
    await queue.enqueue(job)
    if status == "ready":
        await queue.complete(job_id=job.id, contract_hash=job.contract_hash)
    paths = VideoArtifactPaths.for_job(job)
    for path, data in [
        (paths.contracts, contracts.model_dump_json().encode()),
        (paths.timing, timing.model_dump_json().encode()),
    ]:
        await storage.upload(path=path, data=data, content_type="application/json")
    import json

    provenance = {
        "job_id": job.id,
        "course_id": job.course_id,
        "kind": "lesson",
        "lesson_id": "lesson1",
        "model": "fixture",
        "contract_hash": job.contract_hash,
        "input_hash": job.input_hash,
        "generated_at": "2026-09-15T00:00:00Z",
        "degraded_scenes": [{"scene_id": "S1_records", "issues": ["uncertain"]}]
        if degraded
        else [],
    }
    await storage.upload(
        path=paths.provenance, data=json.dumps(provenance).encode(), content_type="application/json"
    )
    return queue, storage


async def test_real_exported_outline_and_measured_mp4_become_clip() -> None:
    queue, storage = await fixture()
    requests = []

    def http(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=mp4())

    async with httpx.AsyncClient(transport=httpx.MockTransport(http)) as client:
        inventory = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="run1")
    assert len(inventory.clips) == 1
    clip = inventory.clips[0]
    assert (clip.start_s, clip.end_s, clip.duration_s) == (0, 2, 2.7)
    assert clip.transcript[0].text == "Records store data."
    assert len(clip.source_digest) == 64
    assert inventory.gaps == ()
    assert len(requests) == 1
    assert "private" not in inventory.model_dump_json()


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"status": "queued"}, "no_ready_video"),
        ({"silent": True}, "silent"),
        ({"degraded": True}, "degraded"),
    ],
)
async def test_unusable_assets_are_explicit_gaps_without_media_download(
    kwargs: dict[str, str | bool], reason: str
) -> None:
    queue, storage = await fixture(**kwargs)

    def no_http(request: httpx.Request) -> httpx.Response:
        pytest.fail("unusable source must not download media")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_http)) as client:
        inventory = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert inventory.clips == ()
    assert inventory.gaps[0].reason == reason


async def test_foreign_course_denied_before_storage() -> None:
    queue, storage = await fixture()
    async with httpx.AsyncClient() as client:
        with pytest.raises(FileNotFoundError):
            await StudioVideoInventory(
                Courses(), queue, storage, SignedVideoMedia(storage, client=client)
            ).load("course1", owner_id="other", run_id="r")
    assert storage.reads == []


@pytest.mark.parametrize(
    "status,headers,body",
    [
        (302, {"location": "https://other.test/private"}, b""),
        (200, {"content-length": "10000000"}, b""),
        (200, {}, b"x" * 101),
        (200, {"content-encoding": "gzip"}, b""),
    ],
)
async def test_media_download_rejects_redirects_and_resource_overruns(
    status: int, headers: dict[str, str], body: bytes
) -> None:
    storage = SignedStorage()
    requests = []

    def http(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, headers=headers, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(http)) as client:
        with pytest.raises(ValueError):
            await SignedVideoMedia(storage, client=client).inspect(
                path="owner/course/job/final.mp4", max_bytes=100
            )
    assert len(requests) == 1


async def test_changed_contract_and_malformed_timing_never_create_candidates() -> None:
    queue, storage = await fixture()
    job = await queue.get(job_id="job1", owner_id="owner1")
    paths = VideoArtifactPaths.for_job(job)
    await storage.upload(
        path=paths.timing,
        data=b'{"S1_records":{"beats":[],"total_s":2}}',
        content_type="application/json",
    )
    async with httpx.AsyncClient() as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert result.clips == ()
    assert result.gaps[0].reason == "malformed_timing"


async def test_latest_ready_replacement_wins_over_old_pointer() -> None:
    queue, storage = await fixture()
    original = await queue.get(job_id="job1", owner_id="owner1")
    replacement = original.model_copy(update={"id": "replacement"})
    await queue.enqueue(replacement)
    await queue.complete(job_id=replacement.id, contract_hash=replacement.contract_hash)
    old_paths, new_paths = (
        VideoArtifactPaths.for_job(original),
        VideoArtifactPaths.for_job(replacement),
    )
    import json

    for attr in ("contracts", "timing", "provenance"):
        content = await storage.download(path=getattr(old_paths, attr))
        if attr == "provenance":
            payload = json.loads(content)
            payload["job_id"] = replacement.id
            content = json.dumps(payload).encode()
        await storage.upload(
            path=getattr(new_paths, attr), data=content, content_type="application/json"
        )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=mp4()))
    ) as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert [clip.job_id for clip in result.clips] == ["replacement"]


async def test_inventory_caps_course_slots_and_records_gap() -> None:
    queue, storage = await fixture(status="queued")
    for index in range(11):
        await queue.enqueue(
            VideoJob(
                id=f"job{index + 2}",
                user_id="owner1",
                course_id="course1",
                lesson_id=f"lesson{index}",
                kind="lesson",
                input_hash="a" * 64,
            )
        )
    async with httpx.AsyncClient() as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert result.clips == ()
    assert len(result.gaps) == 11
    assert result.gaps[0].reason == "inventory_limit"


async def test_stale_missing_lesson_yields_gap_before_storage_access() -> None:
    queue, storage = await fixture(status="queued")
    job = VideoJob(
        id="lesson-job",
        user_id="owner1",
        course_id="course1",
        lesson_id="gone",
        kind="lesson",
        input_hash="a" * 64,
        config={"target_seconds": 90},
    )
    await queue.enqueue(job)
    await queue.complete(job_id=job.id)
    async with httpx.AsyncClient() as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert result.clips == ()
    assert "stale" in [gap.reason for gap in result.gaps]


@pytest.mark.parametrize("changes", [{"id": "different"}, {"status": "diagnosing"}])
async def test_unpublished_or_wrong_course_refused_before_queue(changes: dict[str, str]) -> None:
    courses = Courses()
    courses.course = courses.course.model_copy(update=changes)

    class NeverQueue(InMemoryVideoJobQueue):
        async def list_for_course(self, **kwargs: object) -> list[VideoJob]:
            pytest.fail("invalid course reached queue")

    storage = SignedStorage()
    async with httpx.AsyncClient() as client:
        with pytest.raises(FileNotFoundError):
            await StudioVideoInventory(
                courses, NeverQueue(), storage, SignedVideoMedia(storage, client=client)
            ).load("course1", owner_id="owner1", run_id="r")


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_id", "different"),
        ("course_id", "different"),
        ("input_hash", "f" * 64),
        ("contract_hash", "f" * 64),
    ],
)
async def test_provenance_mismatch_never_downloads_media(field: str, value: str) -> None:
    queue, storage = await fixture()
    job = await queue.get(job_id="job1", owner_id="owner1")
    assert job is not None
    paths = VideoArtifactPaths.for_job(job)
    payload = json.loads(await storage.download(path=paths.provenance))
    payload[field] = value
    await storage.upload(
        path=paths.provenance, data=json.dumps(payload).encode(), content_type="application/json"
    )

    def no_media(request: httpx.Request) -> httpx.Response:
        pytest.fail("untrusted provenance reached MP4")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_media)) as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert not result.clips
    assert result.gaps[0].reason == "stale"


@pytest.mark.parametrize("kind", ["overview", "summary"])
async def test_course_level_video_freshness_is_unverified(kind: str) -> None:
    queue, storage = await fixture(status="queued")
    job = VideoJob(
        id="course-video", user_id="owner1", course_id="course1", kind=kind, input_hash="a" * 64
    )
    await queue.enqueue(job)
    await queue.complete(job_id=job.id)

    def no_media(request: httpx.Request) -> httpx.Response:
        pytest.fail("unbound course video reached media")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_media)) as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert not result.clips
    assert any(gap.job_id == job.id and gap.reason == "stale" for gap in result.gaps)


async def test_changed_contract_bytes_rejected_before_media_download() -> None:
    queue, storage = await fixture()
    job = await queue.get(job_id="job1", owner_id="owner1")
    assert job is not None
    paths = VideoArtifactPaths.for_job(job)
    payload = json.loads(await storage.download(path=paths.contracts))
    payload["topic"] = "Changed topic"
    await storage.upload(
        path=paths.contracts, data=json.dumps(payload).encode(), content_type="application/json"
    )

    def no_media(request: httpx.Request) -> httpx.Response:
        pytest.fail("changed source reached media")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_media)) as client:
        result = await StudioVideoInventory(
            Courses(), queue, storage, SignedVideoMedia(storage, client=client)
        ).load("course1", owner_id="owner1", run_id="r")
    assert not result.clips
    assert result.gaps[0].reason == "stale"
