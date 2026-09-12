"""The production Supabase adapter crosses real REST and Postgres, including ownership checks."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from lunaris_live.sims.registry.supabase_asset_store import SupabaseSimAssetStore
from lunaris_live.sims.schema.build_result import SimBuildResult

from supabase import create_client

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("SUPABASE_TEST_SERVICE_KEY"), reason="Local Supabase REST test key not set"
    ),
]
ROOT = Path(__file__).resolve().parents[2]


def test_store_publishes_reloads_and_revokes_through_real_rest():
    owner, stranger = str(uuid4()), str(uuid4())
    key = uuid4().hex * 2
    result = SimBuildResult.model_validate_json(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    client = create_client(os.environ["SUPABASE_TEST_URL"], os.environ["SUPABASE_TEST_SERVICE_KEY"])
    store = SupabaseSimAssetStore(client=client)
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
        connection.execute("insert into auth.users (id) values (%s)", (owner,))
    try:
        ticket = store.claim(key, owner_id=owner)
        assert ticket is not None
        assert store.claim(key, owner_id=owner) is None
        asset = store.finish(ticket, result)
        assert asset.bundle.candidate.html == result.bundle.candidate.html
        assert store.load(str(asset.id), owner_id=owner) == asset
        assert store.find([key], owner_id=owner) == [asset]
        assert store.find([key], owner_id=stranger) == []
        assert store.find([key], owner_id=None) == []
        with pytest.raises(FileNotFoundError):
            store.load(str(asset.id), owner_id=stranger)
        with pytest.raises(FileNotFoundError):
            store.revoke(str(asset.id), owner_id=stranger)
        store.revoke(str(asset.id), owner_id=owner)
        assert store.find([key], owner_id=owner) == []
        with pytest.raises(FileNotFoundError):
            store.load(str(asset.id), owner_id=owner)
        assert store.claim(key, owner_id=owner) is None
    finally:
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
            connection.execute("delete from auth.users where id=%s", (owner,))
