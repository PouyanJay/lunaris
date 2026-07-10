"""T5 (keyless-fallbacks): the per-course build tag — structural provenance of which provider
produced THIS course.

Distinct from the live capability badge (which reads the *current* key state and flips the moment a
key is stored): this tag is captured at finalize from the run's actual credential scope and persists
on the course, so a Draft course always carries the honest record of the fallback that built it. It
only changes when the course is rebuilt with a real provider.

Driven directly on the finalize tool (deterministic) inside a ``run_credentials`` scope — the same
scope a real build runs in — so ``resolve_secret`` reports exactly the keys the build used. The
device-bridge scope (device-build-bridge T2) layers in the same way: a bridge in scope at finalize
tags the LLM as having run on the learner's device.
"""

from pathlib import Path

import structlog
from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_runtime.capabilities.capability_spec import CAPABILITY_SPECS
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.device_bridge import DeviceBridge, run_device_bridge
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    CapabilityMode,
    CapabilityName,
    KnowledgeComponent,
    PrerequisiteGraph,
)

# The capabilities the course build itself runs (and therefore tags) — COVER is excluded (it
# generates async, so it carries no per-course build tag). Derived from the spec so it can't drift.
_BUILD_TAGGED = {spec.capability for spec in CAPABILITY_SPECS if spec.build_tagged}


def _draft_with_graph(course_id: str, run_id: str) -> CourseDraft:
    draft = CourseDraft(topic="demo", course_id=course_id, run_id=run_id)
    draft.graph = PrerequisiteGraph(
        nodes=[
            KnowledgeComponent(
                id="arrays",
                label="Arrays",
                definition="d",
                difficulty=0.2,
                bloom_ceiling=BloomLevel.UNDERSTAND,
            )
        ],
        edges=[],
        frontier=[],
        is_acyclic=True,
        topo_order=["arrays"],
    )
    return draft


def _finalize_tool(draft: CourseDraft, store: CourseStore):
    return make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())


def _tag(course, capability: CapabilityName):
    return next(t for t in course.build_capabilities if t.capability is capability)


async def test_keyless_build_tags_every_capability_with_its_fallback(tmp_path: Path) -> None:
    # Arrange — a keyless tenant build: an empty credential scope, so resolve_secret reports no
    # provider key (tenant-only, never the platform env). The finalize tool assembles the course.
    store = CourseStore(tmp_path)
    draft = _draft_with_graph("course-keyless", "run-keyless")
    finalize = _finalize_tool(draft, store)

    # Act — finalize inside the keyless run scope (the scope a real keyless build runs in).
    with run_credentials({}):
        await finalize.ainvoke({})
    course = draft.course

    # Assert — every key-gated capability is tagged, the LLM ran on its keyless fallback (the Qwen
    # label), and the tag survives the store round-trip (structural provenance persists).
    assert course is not None
    tagged = {t.capability for t in course.build_capabilities}
    assert tagged == _BUILD_TAGGED
    llm = _tag(course, CapabilityName.LLM)
    assert llm.mode is CapabilityMode.FALLBACK
    assert "Qwen" in llm.provider
    reloaded = store.load("course-keyless")
    assert reloaded.build_capabilities == course.build_capabilities


async def test_a_keyed_capability_is_tagged_live(tmp_path: Path) -> None:
    # Arrange — a tenant who has set their Anthropic key: the run scope carries it, so the LLM
    # capability ran live while the unkeyed ones (embeddings/search/video) stayed on the fallback.
    store = CourseStore(tmp_path)
    draft = _draft_with_graph("course-keyed", "run-keyed")
    finalize = _finalize_tool(draft, store)

    # Act
    with run_credentials({"ANTHROPIC_API_KEY": "sk-tenant-key"}):
        await finalize.ainvoke({})
    course = draft.course

    # Assert — the LLM tag flipped to live with the real provider label; an unkeyed capability is
    # still on its fallback, so the per-course tag records a mixed, honest build.
    assert course is not None
    llm = _tag(course, CapabilityName.LLM)
    assert llm.mode is CapabilityMode.LIVE
    assert llm.provider == "Anthropic Claude"
    search = _tag(course, CapabilityName.SEARCH)
    assert search.mode is CapabilityMode.FALLBACK


async def test_rebuilding_with_a_key_updates_the_persisted_build_tag(tmp_path: Path) -> None:
    # The per-course tag persists but is not frozen: a rebuild re-captures it, so a Draft course
    # rebuilt once a key is set stops advertising the fallback. Re-using the course id is what a
    # rebuild does (same course, fresh run), so the second finalize overwrites the first's tag.
    store = CourseStore(tmp_path)

    # Arrange — the course exists from a keyless first build (the tag records the LLM fallback).
    with run_credentials({}):
        await _finalize_tool(_draft_with_graph("course-rebuilt", "run-1"), store).ainvoke({})
    assert _tag(store.load("course-rebuilt"), CapabilityName.LLM).mode is CapabilityMode.FALLBACK

    # Act — rebuild the same course id with a key now in scope.
    with run_credentials({"ANTHROPIC_API_KEY": "sk-now-keyed"}):
        await _finalize_tool(_draft_with_graph("course-rebuilt", "run-2"), store).ainvoke({})

    # Assert — the persisted tag flipped to live; the stale fallback tag is gone.
    assert _tag(store.load("course-rebuilt"), CapabilityName.LLM).mode is CapabilityMode.LIVE


async def test_finalize_logs_the_fallback_capabilities_run_id_correlated(tmp_path: Path) -> None:
    # The provenance is diagnosable from the structured log: a thin Draft course can be explained by
    # which capabilities ran keyless, correlated by run_id, with no key value ever logged.
    # Arrange
    draft = _draft_with_graph("course-log", "run-log")
    finalize = _finalize_tool(draft, CourseStore(tmp_path))

    # Act
    with structlog.testing.capture_logs() as logs, run_credentials({}):
        await finalize.ainvoke({})

    # Assert — the finalize event carries the run_id and names the keyless capabilities (labels).
    finalized = next(e for e in logs if e["event"] == "agent_course_finalized")
    assert finalized["run_id"] == "run-log"
    assert set(finalized["fallback_capabilities"]) == {c.value for c in _BUILD_TAGGED}


async def test_a_device_compute_build_tags_the_llm_with_the_device_provider(
    tmp_path: Path,
) -> None:
    # Arrange — a keyless DEVICE build: empty credential scope AND the run's device bridge in
    # scope (the learner's browser served the completions). Finalize runs inside both, exactly
    # as a real device build does.
    store = CourseStore(tmp_path)
    draft = _draft_with_graph("course-device", "run-device")
    finalize = _finalize_tool(draft, store)

    # Act
    with run_credentials({}), run_device_bridge(DeviceBridge(run_id="run-device")):
        await finalize.ainvoke({})
    course = draft.course

    # Assert — the LLM tag stays an honest Draft (FALLBACK) but names the learner's device as
    # the provider, distinct from the server tier's "(local)" label; the other capabilities
    # keep their server fallback labels (only the LLM leg moved to the device).
    assert course is not None
    llm = _tag(course, CapabilityName.LLM)
    assert llm.mode is CapabilityMode.FALLBACK
    assert llm.provider == "Qwen2.5-3B (your device)"
    search = _tag(course, CapabilityName.SEARCH)
    assert search.mode is CapabilityMode.FALLBACK
    assert search.provider == "DuckDuckGo"
