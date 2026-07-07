"""End-to-end BYOK proof (Phase 2, T7): the REAL crypto path from the Settings panel to the run.

``test_byok_injection_api`` proves injection with a fake resolver; this suite removes that last
stub: a key set over the real ``PUT /api/credentials`` route is validated, AES-256-GCM-encrypted by
the real ``SecretCipher``, persisted (ciphertext only), then decrypted by the real vault and bound
into the build's run scope — where the pipeline reads it back byte-for-byte. One test, every layer
of the credential path that production exercises, no live Supabase (the in-memory store implements
the same ``ICredentialStore`` contract; the Supabase column mapping is pinned in
``test_credential_store``).
"""

from pathlib import Path

import httpx
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import USER_B as _USER_B
from _auth import auth_headers as _auth
from _doubles import AcceptingValidator
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.credential_vault import CredentialVault
from lunaris_api.dependencies import (
    _byok_credential_resolver,
    get_course_service,
    get_credential_vault,
)
from lunaris_api.secrets import InMemoryCredentialStore, SecretCipher
from lunaris_api.service import CourseService
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunEventStore, InMemoryRunStore
from lunaris_runtime.schema import Clarification, Course, DiscoveryDepth

_TENANT_KEY = "sk-ant-tenant-key-for-the-e2e-9abc"


class _RecordingPipeline:
    """Wraps the stub pipeline, recording what the Anthropic key resolves to inside the scope."""

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
        official_only: bool = False,
    ) -> Course:
        self._sink["anthropic"] = resolve_secret("ANTHROPIC_API_KEY")
        return await self._inner.run(
            topic,
            course_id=course_id,
            run_id=run_id,
            progress=progress,
            agent=agent,
            clarification=clarification,
            discovery_depth=discovery_depth,
        )


def _real_vault(store: InMemoryCredentialStore) -> CredentialVault:
    """The production vault over the REAL cipher (a real 32-byte AES key) — only the provider
    probe is a double (no network)."""
    cipher = SecretCipher(b"\x07" * 32)
    return CredentialVault(store=store, cipher=cipher, validator=AcceptingValidator())


def _build_client(
    tmp_path: Path, vault: CredentialVault, sink: dict[str, str | None]
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()

    def factory(store: object) -> _RecordingPipeline:
        return _RecordingPipeline(build_stub_orchestrator(store), sink)

    service = CourseService(
        CourseStore(tmp_path),
        factory,
        InMemoryRunStore(),
        event_store=InMemoryRunEventStore(),
        # The same wiring dependencies.py uses in production: the vault IS the resolver.
        credential_resolver=_byok_credential_resolver(vault),
    )
    app.dependency_overrides[get_course_service] = lambda: service
    app.dependency_overrides[get_credential_vault] = lambda: vault
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=_JWT_SECRET,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_key_set_via_the_api_is_encrypted_at_rest_and_injected_into_the_build(
    tmp_path: Path,
) -> None:
    # Arrange — the real vault over the real cipher and an inspectable store.
    store = InMemoryCredentialStore()
    sink: dict[str, str | None] = {}

    async with _build_client(tmp_path, _real_vault(store), sink) as client:
        # Act 1 — the user sets their Anthropic key over the real route.
        put = await client.put(
            "/api/credentials/anthropic", json={"value": _TENANT_KEY}, headers=_auth(_USER_A)
        )

        # Assert 1 — accepted + masked; at rest there is ONLY ciphertext (never the plaintext).
        assert put.status_code == 200
        assert put.json() == {"provider": "anthropic", "isSet": True, "last4": _TENANT_KEY[-4:]}
        stored = await store.get(user_id=_USER_A, provider="anthropic")
        assert stored is not None
        assert _TENANT_KEY.encode() not in stored.ciphertext
        assert _TENANT_KEY.encode() not in stored.nonce

        # Act 2 — the same user builds a course.
        build = await client.post("/api/courses", json={"topic": "graphs"}, headers=_auth(_USER_A))

    # Assert 2 — the pipeline saw the tenant's exact key, decrypted from the vault into the run
    # scope: set → validate → encrypt → store → reveal (decrypt) → inject, all real.
    assert build.status_code == 201
    assert sink["anthropic"] == _TENANT_KEY


async def test_another_users_build_never_sees_the_stored_key(tmp_path: Path) -> None:
    # Arrange — A's key is in the vault (through the real encrypt path).
    store = InMemoryCredentialStore()
    sink: dict[str, str | None] = {}

    async with _build_client(tmp_path, _real_vault(store), sink) as client:
        put = await client.put(
            "/api/credentials/anthropic", json={"value": _TENANT_KEY}, headers=_auth(_USER_A)
        )
        assert put.status_code == 200

        # Act — B builds. The vault holds nothing for B; the AAD binds A's blob to A.
        build = await client.post("/api/courses", json={"topic": "graphs"}, headers=_auth(_USER_B))

    # Assert — B's run scope carries NO Anthropic key (a keyless Draft build), never A's.
    assert build.status_code == 201
    assert sink["anthropic"] is None
