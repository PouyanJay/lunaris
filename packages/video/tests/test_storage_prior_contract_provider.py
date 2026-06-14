"""V6-T2: the storage-backed prior-contract provider — the reuse path for Retry / Add narration.

A regenerate job carries the source job's ``scene_contracts.json`` storage path; the provider
downloads + parses it back into the contract type the kind uses (chaptered for the overview, flat
otherwise). Any miss (no path, missing artifact, schema drift) returns ``None`` so the pipeline
re-plans rather than failing the regenerate."""

from lunaris_runtime.persistence import InMemoryVideoStorage, PersistenceError, VideoArtifactPaths
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.schemas import ChapteredSceneContracts, SceneContracts
from lunaris_video.sourcing import StoragePriorContractProvider

_OWNER = "00000000-0000-0000-0000-000000000001"


def _job(kind: VideoKind, *, regenerate: dict[str, object] | None = None) -> VideoJob:
    config: dict[str, object] = {}
    if regenerate is not None:
        config["regenerate"] = regenerate
    return VideoJob(
        id="job-regen",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="lesson-1" if kind is VideoKind.LESSON else None,
        kind=kind,
        input_hash="h",
        config=config,
    )


def _source_job(kind: VideoKind) -> VideoJob:
    return VideoJob(
        id="source-job",
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="lesson-1" if kind is VideoKind.LESSON else None,
        kind=kind,
        input_hash="h",
    )


async def _stage_contract(storage: InMemoryVideoStorage, source: VideoJob, body: bytes) -> str:
    path = VideoArtifactPaths.for_job(source).contracts
    await storage.upload(path=path, data=body, content_type="application/json")
    return path


async def test_loads_and_parses_a_flat_lesson_contract(make_lesson_contract) -> None:
    # Arrange — a prior LESSON job's scene_contracts.json staged in storage.
    storage = InMemoryVideoStorage()
    contract = make_lesson_contract()
    source = _source_job(VideoKind.LESSON)
    path = await _stage_contract(storage, source, contract.model_dump_json().encode())

    # Act — a regenerate job pointing at it.
    loaded = await StoragePriorContractProvider(storage).load(
        _job(VideoKind.LESSON, regenerate={"mode": "retry", "contract_path": path})
    )

    # Assert — the same contract comes back, as the flat type.
    assert isinstance(loaded, SceneContracts)
    assert loaded == contract


async def test_loads_the_overview_contract_as_chaptered(make_chaptered_contract) -> None:
    # The OVERVIEW kind parses the chaptered type, not the flat one.
    storage = InMemoryVideoStorage()
    contract = make_chaptered_contract()
    source = _source_job(VideoKind.OVERVIEW)
    path = await _stage_contract(storage, source, contract.model_dump_json().encode())

    loaded = await StoragePriorContractProvider(storage).load(
        _job(VideoKind.OVERVIEW, regenerate={"mode": "add_narration", "contract_path": path})
    )

    assert isinstance(loaded, ChapteredSceneContracts)
    assert loaded == contract


async def test_returns_none_when_not_a_regenerate() -> None:
    loaded = await StoragePriorContractProvider(InMemoryVideoStorage()).load(_job(VideoKind.LESSON))
    assert loaded is None


async def test_returns_none_without_a_contract_path() -> None:
    loaded = await StoragePriorContractProvider(InMemoryVideoStorage()).load(
        _job(VideoKind.LESSON, regenerate={"mode": "retry"})
    )
    assert loaded is None


async def test_returns_none_when_the_artifact_is_missing() -> None:
    # The path points nowhere (the source's contract was never persisted) → degrade, never raise.
    loaded = await StoragePriorContractProvider(InMemoryVideoStorage()).load(
        _job(VideoKind.LESSON, regenerate={"mode": "retry", "contract_path": "gone/contracts.json"})
    )
    assert loaded is None


async def test_returns_none_when_the_artifact_is_unparseable() -> None:
    storage = InMemoryVideoStorage()
    source = _source_job(VideoKind.LESSON)
    path = await _stage_contract(storage, source, b"{not a contract}")

    loaded = await StoragePriorContractProvider(storage).load(
        _job(VideoKind.LESSON, regenerate={"mode": "retry", "contract_path": path})
    )

    assert loaded is None


class _FailingStorage:
    """A storage double whose download always raises — to prove a read failure degrades to None."""

    async def download(self, *, path: str) -> bytes:
        raise PersistenceError("storage down")


async def test_returns_none_when_the_download_fails() -> None:
    loaded = await StoragePriorContractProvider(_FailingStorage()).load(  # type: ignore[arg-type]
        _job(VideoKind.LESSON, regenerate={"mode": "retry", "contract_path": "x/contracts.json"})
    )
    assert loaded is None
