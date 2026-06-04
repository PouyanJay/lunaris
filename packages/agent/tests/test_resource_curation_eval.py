"""P7.4 — the resource-curation eval (live, key-gated).

The headline guarantee of the "go beyond": for a real lesson, the curator finds genuine external
resources and attaches each with provenance + a "why this helps". Deselected by default; run with a
live Anthropic key AND a SEARCH_API_KEY via ``-m eval`` (a YOUTUBE_API_KEY is optional — without it
videos come through the shared-search fallback). The offline ``test_resource_curator`` suite proves
the orchestration deterministically; this proves the end-to-end outcome against the live web.
"""

import os

import pytest
from lunaris_agent.subagents.resource_curator import ClaudeResourceCurator
from lunaris_grounding import SearchVideoSource, TavilySearchProvider
from lunaris_runtime.schema import BloomLevel, Module, Objective, ResourceKind, TrustTier

pytestmark = pytest.mark.eval

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
_VALID_KINDS = set(ResourceKind)
_VALID_TIERS = set(TrustTier)


async def test_curates_real_resources_with_provenance_and_a_why() -> None:
    # Arrange — a well-resourced CS lesson (real videos/articles abound), with live search + model.
    if not os.getenv("SEARCH_API_KEY"):
        pytest.skip("SEARCH_API_KEY unset; the resource-curation eval needs a live search backend")
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the resource-curation eval needs a live model")
    search = TavilySearchProvider()
    curator = ClaudeResourceCurator(
        os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER),
        search,
        SearchVideoSource(search),
    )
    module = Module(
        id="m-bsearch",
        title="Binary search",
        kcs=["bsearch"],
        competency="locate an element in a sorted array in O(log n) time with binary search",
        objectives=[
            Objective(
                statement="Given a sorted array, the learner can apply binary search.",
                bloom_level=BloomLevel.APPLY,
                kc="bsearch",
            )
        ],
        difficulty_index=0.6,
    )

    # Act
    curated = await curator.curate(module)

    # Assert — at least one resource was vetted in, and every one carries real provenance + a why +
    # a valid kind/tier (the structural guarantees the reader and trust badge rely on).
    all_resources = curated.activate + curated.demonstrate + curated.apply + curated.integrate
    assert all_resources, "the curator attached no resources for a well-resourced topic"
    for resource in all_resources:
        assert resource.url.startswith("http"), f"resource has no real URL: {resource.url}"
        assert resource.fetched_at, "resource is missing its fetched_at provenance stamp"
        assert resource.why.strip(), "resource has no 'why this helps'"
        assert resource.kind in _VALID_KINDS
        assert resource.trust_tier in _VALID_TIERS
        assert resource.trust_tier is not TrustTier.BLOCKED, "a blocked-domain resource shipped"
