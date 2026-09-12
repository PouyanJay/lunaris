"""Approved code is served under the authenticated owner and runtime sandbox policy."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from lunaris_api.app import create_app
from lunaris_api.dependencies import optional_user_id
from lunaris_api.live.session.sim_asset_dependencies import get_sim_asset_store
from lunaris_live.sims.registry.schema.asset import SimAsset

ROOT = Path(__file__).resolve().parents[4]


async def test_private_document_requires_scoped_lookup_and_cannot_be_cached():
    owner = str(uuid4())
    raw = json.loads(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    asset = SimAsset(
        id=uuid4(), owner_id=owner, cache_key="a" * 64, bundle=raw["bundle"], calls=raw["calls"]
    )
    seen = []
    revoked = False

    def load(asset_id, *, owner_id):
        seen.append((asset_id, owner_id))
        if revoked:
            raise FileNotFoundError()
        return asset

    app = create_app()
    app.dependency_overrides[optional_user_id] = lambda: owner
    app.dependency_overrides[get_sim_asset_store] = lambda: SimpleNamespace(load=load)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/api/live/sims/assets/{asset.id}"
        response = await client.get(url, params={"owner_id": str(uuid4())})
        assert response.status_code == 200
        assert seen == [(str(asset.id), owner)]
        assert response.text == asset.bundle.candidate.html
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "sandbox allow-scripts" in response.headers["content-security-policy"]
        assert "connect-src 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
        revoked = True
        assert (await client.get(url)).status_code == 404
