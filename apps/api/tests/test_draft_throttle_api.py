"""T6 (keyless-fallbacks): operator gate + per-tenant throttle for keyless (Draft) builds.

Keyless builds run on a slow, shared local runtime, so a signed-in tenant's Draft builds are
admission-controlled: the operator can switch the tier off entirely, each tenant gets a per-day cap,
and only one keyless build runs at a time (a second concurrent one is refused, not silently piled
onto the runtime). A fully-keyed build is never throttled — it hits the fast hosted provider.

Drives the real HTTP -> service -> pipeline path (like test_byok_injection_api): a BYOK resolver
returning {} is a keyless tenant; a resolver returning an Anthropic key is a keyed one.
"""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path

import httpx
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import auth_headers as _auth
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_service
from lunaris_api.draft_throttle import KeylessBuildThrottle
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore
from lunaris_runtime.schema import Course


def _resolver_returning(
    mapping_by_user: Mapping[str, Mapping[str, str]],
) -> Callable[[str], object]:
    async def resolve(user_id: str) -> dict[str, str]:
        return dict(mapping_by_user.get(user_id, {}))

    return resolve


def _build_client(
    tmp_path: Path,
    *,
    resolver: Callable[[str], object] | None,
    throttle: KeylessBuildThrottle,
    pipeline_factory: Callable[[object], object] | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    factory = pipeline_factory or (lambda store: build_stub_orchestrator(store))
    service = CourseService(
        CourseStore(tmp_path),
        factory,
        InMemoryRunStore(),
        credential_resolver=resolver,
        throttle=throttle,
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


async def test_keyless_build_is_refused_once_the_daily_cap_is_reached(tmp_path: Path) -> None:
    # Arrange — a keyless tenant (no keys) and a cap of one Draft build per day.
    resolver = _resolver_returning({_USER_A: {}})
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=1, max_concurrent=1)

    async with _build_client(tmp_path, resolver=resolver, throttle=throttle) as client:
        # Act — the first keyless build is admitted; the second exceeds the per-day cap.
        first = await client.post("/api/courses", json={"topic": "a"}, headers=_auth(_USER_A))
        second = await client.post("/api/courses", json={"topic": "b"}, headers=_auth(_USER_A))

    # Assert — 201 then 429, the configured limit named in the error so the learner knows why.
    assert first.status_code == 201, first.text
    assert second.status_code == 429, second.text
    assert "Daily Draft build limit reached (1)" in second.json()["detail"]


async def test_keyed_build_is_never_throttled(tmp_path: Path) -> None:
    # Arrange — a tenant who set their Anthropic key, with a cap of one. Keyed builds hit the fast
    # hosted provider, so they are exempt from the keyless runtime's cap.
    resolver = _resolver_returning({_USER_A: {"ANTHROPIC_API_KEY": "key-for-a"}})
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=1, max_concurrent=1)

    async with _build_client(tmp_path, resolver=resolver, throttle=throttle) as client:
        # Act — two keyed builds despite the cap of one.
        first = await client.post("/api/courses", json={"topic": "a"}, headers=_auth(_USER_A))
        second = await client.post("/api/courses", json={"topic": "b"}, headers=_auth(_USER_A))

    # Assert — both succeed; the cap only governs keyless builds.
    assert (first.status_code, second.status_code) == (201, 201), second.text


async def test_keyless_build_is_refused_when_the_operator_disables_the_draft_tier(
    tmp_path: Path,
) -> None:
    # Arrange — the operator has switched Draft builds off.
    resolver = _resolver_returning({_USER_A: {}})
    throttle = KeylessBuildThrottle(enabled=False, daily_cap=10, max_concurrent=1)

    async with _build_client(tmp_path, resolver=resolver, throttle=throttle) as client:
        # Act — a keyless build is rejected up front.
        response = await client.post("/api/courses", json={"topic": "a"}, headers=_auth(_USER_A))

    # Assert — 403 (forbidden by operator policy), not a silent keyless build.
    assert response.status_code == 403, response.text


async def test_stream_refuses_a_keyless_build_before_the_event_stream_opens(tmp_path: Path) -> None:
    # The SSE path admits the build BEFORE the StreamingResponse starts, so an operator-disabled
    # keyless build is a real 403 — not a 200 stream that drops mid-flight (which the client can't
    # tell from a network error).
    resolver = _resolver_returning({_USER_A: {}})
    throttle = KeylessBuildThrottle(enabled=False, daily_cap=10, max_concurrent=1)

    async with _build_client(tmp_path, resolver=resolver, throttle=throttle) as client:
        # Act — a keyless SSE build is rejected up front.
        response = await client.get(
            "/api/courses/stream", params={"topic": "a"}, headers=_auth(_USER_A)
        )

    # Assert — a proper HTTP status, not an opened event stream.
    assert response.status_code == 403, response.text


class _BlockingPipeline:
    """A stub-backed pipeline that signals once it holds the slot, then parks on a release event —
    a deterministic gate (no sleeps) for the serialization test."""

    def __init__(self, inner: object, *, reserved: asyncio.Event, release: asyncio.Event) -> None:
        self._inner = inner
        self._reserved = reserved
        self._release = release

    async def run(self, topic: str, **kwargs: object) -> Course:
        self._reserved.set()  # the slot is held → the test may now fire the concurrent request
        await self._release.wait()
        return await self._inner.run(topic, **kwargs)


async def test_a_second_concurrent_keyless_build_is_refused_while_one_is_running(
    tmp_path: Path,
) -> None:
    # Arrange — one keyless build is held in-flight; a second concurrent one must be refused so the
    # shared CPU runtime serves one Draft build at a time, rather than piling builds onto it.
    resolver = _resolver_returning({_USER_A: {}})
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=10, max_concurrent=1)
    reserved = asyncio.Event()
    release = asyncio.Event()

    def factory(store: object) -> _BlockingPipeline:
        return _BlockingPipeline(build_stub_orchestrator(store), reserved=reserved, release=release)

    async with _build_client(
        tmp_path, resolver=resolver, throttle=throttle, pipeline_factory=factory
    ) as client:
        # Act — start the first build and wait until it has deterministically reserved its slot,
        # then attempt a second while it is held in-flight.
        first = asyncio.create_task(
            client.post("/api/courses", json={"topic": "a"}, headers=_auth(_USER_A))
        )
        await reserved.wait()
        second = await client.post("/api/courses", json={"topic": "b"}, headers=_auth(_USER_A))
        release.set()  # let the first build finish
        first_response = await first

    # Assert — the in-flight build wins the single slot; the concurrent one is refused (429).
    assert first_response.status_code == 201, first_response.text
    assert second.status_code == 429, second.text
