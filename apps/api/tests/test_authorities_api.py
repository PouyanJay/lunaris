"""P6.2 Trusted-sources API: list / upsert / delete over the real ASGI app with an in-memory trust
config (no Supabase key). The boundary validation (pack-has-field → 422) is pinned here too."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_authority_store
from lunaris_grounding import InMemorySourceAuthorityStore
from lunaris_runtime.logging import clear_correlation

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def _app(tmp_path: Path) -> FastAPI:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
    )
    # One shared store for the app's lifetime, so an upsert is visible to a later list/delete (a
    # fresh instance per request would lose every write — the prod stores are process singletons).
    store = InMemorySourceAuthorityStore()
    app.dependency_overrides[get_authority_store] = lambda: store
    return app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(tmp_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_upsert_then_list_round_trips_a_spine_authority(client: httpx.AsyncClient) -> None:
    # Arrange — a fresh empty store (the fixture's app).
    # Act — add a global spine authority, then list.
    put = await client.put(
        "/api/source-authorities",
        json={"domain": "EN.Wikipedia.org", "kind": "spine", "tier": "reputable"},
    )
    listed = await client.get("/api/source-authorities")

    # Assert — created, normalised (lowercased), and surfaced on the list with its tier. Both
    # responses carry a well-formed correlation id (CLAUDE.md "correlation everywhere").
    assert put.status_code == 200
    assert put.json()["domain"] == "en.wikipedia.org"
    assert _REQUEST_ID.fullmatch(put.headers["X-Request-Id"])
    assert _REQUEST_ID.fullmatch(listed.headers["X-Request-Id"])
    rows = listed.json()
    assert [r["domain"] for r in rows] == ["en.wikipedia.org"]
    assert rows[0]["tier"] == "reputable"
    assert rows[0]["field"] is None


async def test_upsert_replaces_an_existing_row_by_domain_and_field(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — a medicine pack authority.
    base = {"domain": "pubmed.ncbi.nlm.nih.gov", "kind": "pack", "field": "medicine"}
    await client.put("/api/source-authorities", json={**base, "tier": "reputable"})

    # Act — re-submit the same (domain, field) with a different tier → replace, not duplicate.
    await client.put("/api/source-authorities", json={**base, "tier": "official"})
    rows = (await client.get("/api/source-authorities")).json()

    # Assert — one row, updated tier.
    assert len(rows) == 1
    assert rows[0]["tier"] == "official"


async def test_delete_removes_a_row_by_key(client: httpx.AsyncClient) -> None:
    # Arrange
    await client.put(
        "/api/source-authorities", json={"domain": "bit.ly", "kind": "denylist", "tier": "blocked"}
    )

    # Act — delete it, then delete the same key AGAIN (it's already gone).
    deleted = await client.request("DELETE", "/api/source-authorities", params={"domain": "bit.ly"})
    again = await client.request("DELETE", "/api/source-authorities", params={"domain": "bit.ly"})
    rows = (await client.get("/api/source-authorities")).json()

    # Assert — the row is gone, and deleting an absent key is idempotent (204, not 404).
    assert deleted.status_code == 204
    assert again.status_code == 204
    assert _REQUEST_ID.fullmatch(deleted.headers["X-Request-Id"])
    assert rows == []


async def test_a_pack_without_a_field_is_rejected_at_the_boundary(
    client: httpx.AsyncClient,
) -> None:
    # Act — a pack with no field violates the invariant; the request validator must 422 it.
    response = await client.put(
        "/api/source-authorities",
        json={"domain": "example.com", "kind": "pack", "tier": "official"},
    )

    # Assert
    assert response.status_code == 422


async def test_a_spine_with_a_field_is_rejected_at_the_boundary(client: httpx.AsyncClient) -> None:
    # Act — a non-pack with a field is equally invalid.
    response = await client.put(
        "/api/source-authorities",
        json={"domain": "example.com", "kind": "spine", "tier": "official", "field": "medicine"},
    )

    # Assert
    assert response.status_code == 422


async def test_an_out_of_vocab_enum_is_rejected_at_the_boundary(client: httpx.AsyncClient) -> None:
    # Act — a tier outside the StrEnum vocabulary is a 422 (the request schema validates it).
    response = await client.put(
        "/api/source-authorities",
        json={"domain": "example.com", "kind": "spine", "tier": "platinum"},
    )

    # Assert
    assert response.status_code == 422


async def test_a_blank_domain_is_rejected_at_the_boundary(client: httpx.AsyncClient) -> None:
    # Act — an empty domain fails the min_length=1 field constraint.
    response = await client.put(
        "/api/source-authorities", json={"domain": "", "kind": "spine", "tier": "open"}
    )

    # Assert
    assert response.status_code == 422
