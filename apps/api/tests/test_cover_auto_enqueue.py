"""Auto-enqueue a course cover at build completion (course-cover-images T8).

Traverses the real ``CourseService.create``/``stream`` → build (the deterministic stub orchestrator,
which persists a real Course) → ``_maybe_enqueue_cover`` over the in-memory cover queue. The gate
mirrors video's: an operator flag (``cover_generation_enabled``), a known owner, and a build **keyed
for OpenAI** (covers need GPT Image 2 — never a keyless build). A cover is best-effort and generated
async, so a failure to enqueue never breaks the build.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import CourseStore, InMemoryCoverJobQueue, InMemoryRunStore
from lunaris_runtime.schema import CoverJob, CoverJobStatus, CoverStylePreset

_OWNER = "00000000-0000-0000-0000-00000000000a"
_OPENAI_ENV = "OPENAI_API_KEY"


def _service(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    *,
    cover_generation_enabled: bool = True,
    credential_resolver=None,
    config_resolver=None,
) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        cover_job_queue=queue,
        cover_generation_enabled=cover_generation_enabled,
        credential_resolver=credential_resolver,
        config_resolver=config_resolver,
    )


async def _build(service: CourseService, *, owner_id: str | None) -> str:
    course_id = "course-t8"
    await service.create("How HTTPS works", course_id=course_id, run_id="run-1", owner_id=owner_id)
    return course_id


async def test_keyed_build_auto_enqueues_a_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")  # keyed for OpenAI via the process env (no vault)
    queue = InMemoryCoverJobQueue()
    course_id = await _build(_service(tmp_path, queue), owner_id=_OWNER)

    job = await queue.find_active(course_id=course_id, owner_id=_OWNER)
    assert job is not None
    assert job.status is CoverJobStatus.QUEUED
    assert job.style_preset is CoverStylePreset.NOCTURNE  # T10 wires the per-user preset
    assert job.input_hash  # fingerprints the generation inputs


async def test_keyless_openai_build_enqueues_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_OPENAI_ENV, raising=False)  # no OpenAI key → keyless for covers
    queue = InMemoryCoverJobQueue()
    course_id = await _build(_service(tmp_path, queue), owner_id=_OWNER)

    assert await queue.find_active(course_id=course_id, owner_id=_OWNER) is None


async def test_operator_flag_off_enqueues_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")
    queue = InMemoryCoverJobQueue()
    service = _service(tmp_path, queue, cover_generation_enabled=False)
    course_id = await _build(service, owner_id=_OWNER)

    assert await queue.find_active(course_id=course_id, owner_id=_OWNER) is None


async def test_unowned_build_enqueues_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")
    queue = InMemoryCoverJobQueue()
    course_id = await _build(_service(tmp_path, queue), owner_id=None)

    assert await queue.find_active(course_id=course_id, owner_id=None) is None


async def test_byok_openai_key_makes_the_build_keyed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_OPENAI_ENV, raising=False)  # no env key — the vault provides it

    async def resolver(user_id: str) -> Mapping[str, str]:
        return {_OPENAI_ENV: "sk-tenant"}

    queue = InMemoryCoverJobQueue()
    service = _service(tmp_path, queue, credential_resolver=resolver)
    course_id = await _build(service, owner_id=_OWNER)

    assert await queue.find_active(course_id=course_id, owner_id=_OWNER) is not None


async def test_a_cover_already_in_flight_is_not_re_enqueued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")
    queue = InMemoryCoverJobQueue()
    # A cover job is already active for this course (e.g. a manual enqueue before the build ends).
    await queue.enqueue(
        CoverJob(id="pre-existing", user_id=_OWNER, course_id="course-t8", input_hash="h")
    )
    await _build(_service(tmp_path, queue), owner_id=_OWNER)

    jobs = await queue.list_for_course(course_id="course-t8", owner_id=_OWNER)
    assert [j.id for j in jobs] == ["pre-existing"]  # deduped — no second job


async def test_per_user_toggle_off_enqueues_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The owner turned cover generation off in Settings (T10) — even keyed + operator-on, no cover.
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")

    async def config(user_id: str) -> Mapping[str, str]:
        return {"LUNARIS_COVER_ENABLED": "false"}

    queue = InMemoryCoverJobQueue()
    service = _service(tmp_path, queue, config_resolver=config)
    course_id = await _build(service, owner_id=_OWNER)

    assert await queue.find_active(course_id=course_id, owner_id=_OWNER) is None


async def test_per_user_style_preset_is_stamped_on_the_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")

    async def config(user_id: str) -> Mapping[str, str]:
        return {"LUNARIS_COVER_STYLE_PRESET": "blueprint"}

    queue = InMemoryCoverJobQueue()
    service = _service(tmp_path, queue, config_resolver=config)
    course_id = await _build(service, owner_id=_OWNER)

    job = await queue.find_active(course_id=course_id, owner_id=_OWNER)
    assert job is not None and job.style_preset is CoverStylePreset.BLUEPRINT


async def test_stream_build_also_auto_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The durable path (a client may disconnect mid-build) must enqueue too — the build task, not
    # the viewer generator, owns the enqueue.
    monkeypatch.setenv(_OPENAI_ENV, "sk-test")
    queue = InMemoryCoverJobQueue()
    service = _service(tmp_path, queue)

    async for _ in service.stream(
        "How HTTPS works", course_id="course-t8", run_id="run-1", owner_id=_OWNER
    ):
        pass

    assert await queue.find_active(course_id="course-t8", owner_id=_OWNER) is not None
