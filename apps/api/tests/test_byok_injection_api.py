"""Integration tests for per-run BYOK credential injection (Phase 2, T7).

A build runs on the *current user's* keys, decrypted from the vault and bound to the run's context —
never the process-global platform key. These tests drive the real HTTP → service → pipeline path
with a recording pipeline that reads the run scope, proving:

- the tenant's Anthropic key reaches the build (and the platform env key does not leak into it);
- two users' builds run on their own keys (isolation);
- an optional key the user hasn't set is absent in the scope (honest degradation, not a fallback);
- a build is refused with a clean 400 — both await-full and pre-stream — when the required key is
  unset, so a tenant without keys can't start a (failing) paid build.

Hermetic like ``test_user_isolation_api`` (HS256 tokens, no live Supabase); the credential resolver
is a fake so no cipher/store is needed.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import USER_B as _USER_B
from _auth import auth_headers as _auth
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_service
from lunaris_api.service import CourseService, ProviderKeyRequiredError
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import InMemoryRunEventStore, InMemoryRunStore
from lunaris_runtime.schema import Clarification, Course, DiscoveryDepth


class _RecordingPipeline:
    """Wraps the stub pipeline, recording what each provider key resolves to inside the scope."""

    def __init__(self, inner: object, sink: dict[str, str | None]) -> None:
        self._inner = inner
        self._sink = sink

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: object | None = None,
        agent: object | None = None,
        clarification: Clarification | None = None,
        discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD,
    ) -> Course:
        # Read from the run's credential context — the value the live adapters would see.
        self._sink["anthropic"] = resolve_secret("ANTHROPIC_API_KEY")
        self._sink["search"] = resolve_secret("SEARCH_API_KEY")
        return await self._inner.run(
            topic,
            course_id=course_id,
            run_id=run_id,
            progress=progress,
            agent=agent,
            clarification=clarification,
            discovery_depth=discovery_depth,
        )


def _build_client(
    tmp_path: Path,
    *,
    resolver: Callable[[str], object] | None,
    sink: dict[str, str | None],
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()

    def factory(store: object) -> _RecordingPipeline:
        return _RecordingPipeline(build_stub_orchestrator(store), sink)

    service = CourseService(
        _file_store(tmp_path),
        factory,
        InMemoryRunStore(),
        event_store=InMemoryRunEventStore(),
        credential_resolver=resolver,
    )
    app.dependency_overrides[get_course_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=_JWT_SECRET,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _file_store(tmp_path: Path) -> object:
    from lunaris_runtime.persistence import CourseStore

    return CourseStore(tmp_path)


def _resolver_returning(
    mapping_by_user: Mapping[str, Mapping[str, str]],
) -> Callable[[str], object]:
    async def resolve(user_id: str) -> dict[str, str]:
        return dict(mapping_by_user.get(user_id, {}))

    return resolve


@pytest.fixture
async def _env_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    # A platform key in the environment, to prove a tenant build never falls back to it.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)


async def test_build_runs_on_the_tenants_own_anthropic_key(
    tmp_path: Path, _env_anthropic: None
) -> None:
    # Arrange — user A has set their own Anthropic key; the platform key is in the env.
    sink: dict[str, str | None] = {}
    resolver = _resolver_returning({_USER_A: {"ANTHROPIC_API_KEY": "key-for-a"}})

    # Act — build as A.
    async with _build_client(tmp_path, resolver=resolver, sink=sink) as client:
        response = await client.post(
            "/api/courses", json={"topic": "graphs"}, headers=_auth(_USER_A)
        )

    # Assert — the run saw A's key, not the platform env key.
    assert response.status_code == 201, response.text
    assert sink["anthropic"] == "key-for-a"


async def test_two_users_build_on_their_own_keys(tmp_path: Path, _env_anthropic: None) -> None:
    # Arrange — each user has set a distinct Anthropic key.
    resolver = _resolver_returning(
        {
            _USER_A: {"ANTHROPIC_API_KEY": "key-for-a"},
            _USER_B: {"ANTHROPIC_API_KEY": "key-for-b"},
        }
    )

    # Act — each user builds a course.
    sink_a: dict[str, str | None] = {}
    async with _build_client(tmp_path, resolver=resolver, sink=sink_a) as client:
        await client.post("/api/courses", json={"topic": "a"}, headers=_auth(_USER_A))
    sink_b: dict[str, str | None] = {}
    async with _build_client(tmp_path, resolver=resolver, sink=sink_b) as client:
        await client.post("/api/courses", json={"topic": "b"}, headers=_auth(_USER_B))

    # Assert — each run saw its own owner's key.
    assert (sink_a["anthropic"], sink_b["anthropic"]) == ("key-for-a", "key-for-b")


async def test_optional_key_absent_in_scope_does_not_fall_back_to_env(
    tmp_path: Path, _env_anthropic: None
) -> None:
    # The user set Anthropic but not Search; the build still runs, and Search resolves to None in
    # the scope (honest degradation), never the platform env Search key.
    sink: dict[str, str | None] = {}
    resolver = _resolver_returning({_USER_A: {"ANTHROPIC_API_KEY": "key-for-a"}})

    async with _build_client(tmp_path, resolver=resolver, sink=sink) as client:
        response = await client.post("/api/courses", json={"topic": "x"}, headers=_auth(_USER_A))

    assert response.status_code == 201, response.text
    assert sink["search"] is None


async def test_build_refused_400_when_required_key_unset(
    tmp_path: Path, _env_anthropic: None
) -> None:
    # The tenant has set no keys → the await-full build is refused before it starts.
    sink: dict[str, str | None] = {}
    resolver = _resolver_returning({_USER_A: {}})

    async with _build_client(tmp_path, resolver=resolver, sink=sink) as client:
        response = await client.post("/api/courses", json={"topic": "x"}, headers=_auth(_USER_A))

    assert response.status_code == 400
    assert "Anthropic" in response.json()["detail"]
    assert sink == {}  # the pipeline never ran


async def test_stream_refused_400_before_streaming_when_required_key_unset(
    tmp_path: Path, _env_anthropic: None
) -> None:
    # The SSE pre-flight returns a clean 400 (not an error frame mid-stream).
    sink: dict[str, str | None] = {}
    resolver = _resolver_returning({_USER_A: {}})

    async with _build_client(tmp_path, resolver=resolver, sink=sink) as client:
        response = await client.get(
            "/api/courses/stream", params={"topic": "x"}, headers=_auth(_USER_A)
        )

    assert response.status_code == 400
    assert "Anthropic" in response.json()["detail"]  # the action-prompting message, not a 422
    assert sink == {}  # the pipeline never ran


async def test_no_resolver_runs_on_env_with_no_scope(tmp_path: Path, _env_anthropic: None) -> None:
    # Arrange — BYOK off (no resolver); the platform key is in the env.
    sink: dict[str, str | None] = {}

    # Act — an authenticated user builds.
    async with _build_client(tmp_path, resolver=None, sink=sink) as client:
        response = await client.post("/api/courses", json={"topic": "x"}, headers=_auth(_USER_A))

    # Assert — the build runs on the process env key (today's path, unchanged).
    assert response.status_code == 201, response.text
    assert sink["anthropic"] == "platform-key"


class _FakeRegenerator:
    """A pipeline that can regenerate a lesson, recording the key it sees in the run scope."""

    def __init__(self, sink: dict[str, str | None]) -> None:
        self._sink = sink

    async def regenerate_lesson(self, course_id: str, lesson_id: str, *, run_id: str) -> None:
        self._sink["anthropic"] = resolve_secret("ANTHROPIC_API_KEY")
        return None


async def test_regenerate_runs_in_the_tenant_scope(tmp_path: Path, _env_anthropic: None) -> None:
    # Arrange — a regen-capable pipeline + a BYOK tenant with their own key.
    sink: dict[str, str | None] = {}
    service = CourseService(
        _file_store(tmp_path),
        lambda store: _FakeRegenerator(sink),
        credential_resolver=_resolver_returning({_USER_A: {"ANTHROPIC_API_KEY": "key-for-a"}}),
    )

    # Act — regenerate a lesson as the tenant.
    await service.regenerate_lesson("course-1", "lesson-1", run_id="run-1", owner_id=_USER_A)

    # Assert — the re-author saw the tenant's key, not the platform env key.
    assert sink["anthropic"] == "key-for-a"


async def test_regenerate_refused_when_required_key_unset(
    tmp_path: Path, _env_anthropic: None
) -> None:
    # A BYOK tenant with no keys can't regenerate, exactly as they can't build.
    sink: dict[str, str | None] = {}
    service = CourseService(
        _file_store(tmp_path),
        lambda store: _FakeRegenerator(sink),
        credential_resolver=_resolver_returning({_USER_A: {}}),
    )

    with pytest.raises(ProviderKeyRequiredError):
        await service.regenerate_lesson("course-1", "lesson-1", run_id="run-1", owner_id=_USER_A)
    assert sink == {}  # the pipeline never ran
