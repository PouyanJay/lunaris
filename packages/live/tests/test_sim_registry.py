"""Published assets share code, never learner state or private teaching context."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from lunaris_live.graph.schema import ConceptNode, MasteryCriterion
from lunaris_live.sims.registry.cache_key import sim_cache_key
from lunaris_live.sims.registry.models.versions import SimVersions
from lunaris_live.sims.registry.preloaded_registry import PreloadedSimRegistry
from lunaris_live.sims.registry.schema.asset import SimAsset
from lunaris_live.sims.schema.verified_bundle import VerifiedBundle

ROOT = Path(__file__).resolve().parents[3]


def sample():
    raw = json.loads(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    bundle = VerifiedBundle.model_validate(raw["bundle"])
    node = ConceptNode(id="one", name="Linear relationship", definition="y = 2x")
    criterion = MasteryCriterion(
        kind="manipulate", statement=bundle.spec.contract.objective, needs_sim=True
    )
    return node, criterion, bundle, raw["calls"]


def test_public_reuse_has_fresh_references_and_semantic_identity():
    node, criterion, bundle, calls = sample()
    asset = SimAsset(
        id=uuid4(),
        cache_key=sim_cache_key(node, criterion),
        bundle=bundle,
        calls=calls,
        public_source="reviewed:linear-v1",
    )
    first = PreloadedSimRegistry([asset], owner_id=str(uuid4()))
    second = PreloadedSimRegistry([asset], owner_id=str(uuid4()))
    one = first.app_for(node, criterion)
    two = second.app_for(node.model_copy(update={"id": "another-map-node"}), criterion)
    assert one.app_id == two.app_id
    one.contract.parameters["x"].default = 0
    assert two.contract.parameters["x"].default != 0
    assert second.app_for(node, criterion).contract.parameters["x"].default != 0


@pytest.mark.parametrize("change", ["objective", "definition", "version", "revoked", "private"])
def test_incompatible_revoked_and_private_assets_are_not_selected(change):
    node, criterion, bundle, calls = sample()
    owner = str(uuid4())
    asset = SimAsset(
        id=uuid4(),
        cache_key=sim_cache_key(node, criterion),
        bundle=bundle,
        calls=calls,
        owner_id=owner,
    )
    lookup_owner = owner
    if change == "objective":
        criterion = criterion.model_copy(update={"statement": "Different objective"})
    elif change == "definition":
        node = node.model_copy(update={"definition": "y = 3x"})
    elif change == "version":
        asset = asset.model_copy(
            update={
                "cache_key": sim_cache_key(node, criterion, versions=SimVersions(factory="future"))
            }
        )
    elif change == "revoked":
        asset = asset.model_copy(update={"revoked": True})
    else:
        lookup_owner = str(uuid4())
    assert PreloadedSimRegistry([asset], owner_id=lookup_owner).app_for(node, criterion) is None


def test_private_source_cannot_be_marked_public():
    node, criterion, bundle, calls = sample()
    with pytest.raises(ValueError, match="private"):
        SimAsset(
            id=uuid4(),
            cache_key=sim_cache_key(node, criterion),
            bundle=bundle,
            calls=calls,
            owner_id=str(uuid4()),
            public_source="accidental-publication",
        )


def test_unverified_mutated_bundle_cannot_enter_preloaded_lookup():
    node, criterion, bundle, calls = sample()
    asset = SimAsset(
        id=uuid4(), cache_key=sim_cache_key(node, criterion), bundle=bundle, calls=calls
    )
    asset.bundle.candidate.html += "changed"
    with pytest.raises(ValueError, match="Visual approval must match"):
        PreloadedSimRegistry([asset], owner_id=None)
