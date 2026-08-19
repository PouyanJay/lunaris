"""What a Live compile costs, and whose ledger it lands on (D2, T8b).

A cold compile is one decomposition call plus one per concept — a dozen or more paid calls — and
until now Live spent that money invisibly: no ledger rows, no rollup, nothing to answer "what has
this cost me". Studio's metering seam already does the pricing (the callback on every built chat
model calls ``record_cost``), so what this task adds is the scope that seam needs and the key it
records under: the graph, never the course namespace.

The compiler here is a double that spends deliberately. The callback→``record_cost`` path belongs
to Studio's suites; what is proved here is the wiring the *service* owns — that a scope is opened
around the compile, keyed to the graph, drained afterwards, and attributed to the right pocket.

One thing these do NOT prove: the ``component`` labels. The double chooses its own ("decompose",
"extend"), where a real compile records whatever ``build_chat_model`` was given — today a single
``"llm"`` for every call. Per-phase labels are a follow-up, and reading this suite as evidence of
them would be reading the double's behaviour as production's.
"""

import asyncio
import base64
import time
import uuid
from pathlib import Path

import pytest
from lunaris_api.live.service import LiveGraphService
from lunaris_live.graph import ConceptGraph, ConceptNode, MemoryGraphStore
from lunaris_runtime.credentials import credentials_for, resolve_secret
from lunaris_runtime.metering import record_cost
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType, CostUnit

_TOKENS = 1000.0

#: A valid 32-byte at-rest master key — the switch that turns BYOK on (see the wiring test).
_MASTER_KEY_B64 = base64.b64encode(bytes(32)).decode()

#: A fixed id for the compile whose failure means the caller never learns the real one.
_FIXED_GRAPH_UUID = uuid.UUID("00000000-0000-4000-8000-00000000beef")


class SpendingCompiler:
    """A compiler that bills for its work, the way the real one does through the model callback."""

    def __init__(self, *, fail: bool = False, fail_on_extend: bool = False) -> None:
        self._fail = fail
        self._fail_on_extend = fail_on_extend

    async def compile(self, topic: str, *, graph_id: str, run_id: str, **kwargs: object):
        record_cost(
            component="decompose",
            provider=CostProvider.ANTHROPIC,
            model="claude-opus-4-8",
            usage={CostUnit.INPUT_TOKENS: _TOKENS},
        )
        if self._fail:
            raise TimeoutError("the compile overran after it had already spent")
        return ConceptGraph(
            graph_id=graph_id,
            topic=topic,
            nodes=[ConceptNode(id="a", name="A", definition="A concept.")],
            topo_order=["a"],
            is_acyclic=True,
        )

    async def extend(self, graph: ConceptGraph, *, request: str, anchors, run_id: str):
        record_cost(
            component="extend",
            provider=CostProvider.ANTHROPIC,
            model="claude-opus-4-8",
            usage={CostUnit.INPUT_TOKENS: _TOKENS},
        )
        if self._fail_on_extend:
            raise TimeoutError("the extension overran after it had already spent")
        added = ConceptNode(id="b", name="B", definition="Asked for mid-session.")
        return graph.model_copy(
            update={
                "nodes": [*graph.nodes, added],
                "version": graph.version + 1,
                "topo_order": [*graph.topo_order, "b"],
            }
        )


def _service(
    **kwargs: object,
) -> tuple[LiveGraphService, InMemoryCostEventStore, InMemorySubjectCostStore]:
    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = LiveGraphService(
        SpendingCompiler(**kwargs),  # type: ignore[arg-type]
        MemoryGraphStore(),
        cost_event_store=ledger,
        subject_cost_store=rollup,
    )
    return service, ledger, rollup


async def test_a_compile_lands_on_the_ledger_keyed_to_the_graph() -> None:
    """The task's whole point: a graph's spend is a *graph's*, not a course's.

    A course id and a graph id come from independent sequences, so recording this under the course
    namespace would eventually merge two products' money in rows nobody may correct.
    """
    # Arrange
    service, ledger, rollup = _service()

    # Act
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Assert — the ledger row names the graph it was spent on...
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert [(e.component, e.subject_type) for e in events] == [
        ("decompose", CostSubjectType.LIVE_GRAPH)
    ]
    assert events[0].amount > 0, "a metered call priced at zero would make this test vacuous"

    # ...and the rollup answers for that graph, not for a course of the same id.
    total = await rollup.get(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert total is not None and total.total_amount == pytest.approx(events[0].amount)
    assert (
        await rollup.get(
            subject_type=CostSubjectType.COURSE, subject_id=graph.graph_id, owner_id="alice"
        )
    ) is None


async def test_a_compile_that_fails_still_records_what_it_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The money is gone whether or not the learner got a map. A compile that times out after ten
    of its twelve calls has really spent that, and a ledger that only records successes would
    under-report exactly the runs worth investigating."""
    # Arrange — the graph id is minted inside the service and the call raises before returning it,
    # so it is pinned here rather than fished out of the store's internals afterwards.
    monkeypatch.setattr("lunaris_api.live.service.uuid4", lambda: _FIXED_GRAPH_UUID)
    service, ledger, _ = _service(fail=True)

    # Act
    with pytest.raises(TimeoutError):
        await service.compile("Tides", run_id="r1", owner_id="alice")

    # Assert — one row, for the call that happened before the failure.
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id=_FIXED_GRAPH_UUID.hex,
        owner_id="alice",
    )
    assert [e.component for e in events] == ["decompose"]


async def test_an_extension_adds_to_the_same_graph_s_total() -> None:
    """C1's runtime extension spends too, and it is spend on the same map — so it accumulates on
    that graph's rollup rather than opening a second one."""
    # Arrange
    service, ledger, rollup = _service()
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Act
    await service.extend(
        graph.graph_id,
        request="how do I pick a learning rate?",
        anchors=[],
        run_id="r2",
        owner_id="alice",
    )

    # Assert
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert sorted(e.component for e in events) == ["decompose", "extend"]
    total = await rollup.get(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert total is not None
    assert total.total_amount == pytest.approx(sum(e.amount for e in events))


async def test_an_extension_that_fails_still_records_what_it_spent() -> None:
    """The same guarantee as the compile's, on the path that runs far more often.

    C1 makes extending the map a repeated, mid-session capability, so it is the *bigger* attribution
    surface of the two — and an extension that overran its 15-second budget has still paid for the
    calls it made before the clock ran out.
    """
    # Arrange
    service, ledger, _ = _service(fail_on_extend=True)
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Act
    with pytest.raises(TimeoutError):
        await service.extend(
            graph.graph_id,
            request="what about momentum?",
            anchors=[],
            run_id="r2",
            owner_id="alice",
        )

    # Assert — the failed extension's spend is on the record beside the compile's.
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert sorted(e.component for e in events) == ["decompose", "extend"]


async def test_an_extension_on_a_tenant_s_own_key_pays_from_their_pocket() -> None:
    """Attribution has to hold on the repeated path too. An extension is one to five model calls
    every time a learner asks for something off the map — bill those to the platform and a busy
    session quietly spends the platform's money all afternoon."""

    # Arrange
    async def resolve(user_id: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": f"sk-{user_id}"}

    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = LiveGraphService(
        SpendingCompiler(),  # type: ignore[arg-type]
        MemoryGraphStore(),
        cost_event_store=ledger,
        subject_cost_store=rollup,
        credential_resolver=resolve,
    )
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Act
    await service.extend(
        graph.graph_id, request="what about momentum?", anchors=[], run_id="r2", owner_id="alice"
    )

    # Assert — both the compile and the extension came out of the tenant's own pocket.
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert {e.pocket for e in events} == {CostPocket.USER_KEY}
    assert len(events) == 2


async def test_an_empty_vault_is_not_the_same_as_byok_being_off() -> None:
    """The distinction the pocket alone cannot show.

    A tenant who has set no keys yields an empty *scope*; BYOK being off yields no scope at all.
    Both end up recording ``platform``, so asserting the pocket cannot tell them apart — but they
    differ where it matters: the first must NOT reach the process environment, the second must.
    """

    # Arrange
    async def resolve(user_id: str) -> dict[str, str]:
        return {}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-platform")
    try:
        # Act / Assert — inside the tenant's scope the key is ABSENT, not the platform's: the
        # compiler is bound to the tenant's (empty) vault rather than falling through to whatever
        # the process happens to have.
        with await credentials_for(resolve, "alice"):
            assert resolve_secret("ANTHROPIC_API_KEY") is None
        # ...and with no resolver at all, the environment — which is what lets local dev run.
        with await credentials_for(None, "alice"):
            assert resolve_secret("ANTHROPIC_API_KEY") == "sk-platform"
    finally:
        monkeypatch.undo()


async def test_a_tenant_s_own_key_pays_from_their_own_pocket() -> None:
    """BYOK attribution. A compile that ran on the tenant's key but recorded as ``platform`` would
    bill the platform for money it never spent — and hide the tenant's real usage from them."""

    # Arrange — a resolver standing in for the vault, as the composition root wires it.
    async def resolve(user_id: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": f"sk-{user_id}"}

    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = LiveGraphService(
        SpendingCompiler(),  # type: ignore[arg-type]
        MemoryGraphStore(),
        cost_event_store=ledger,
        subject_cost_store=rollup,
        credential_resolver=resolve,
    )

    # Act
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Assert
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert [e.pocket for e in events] == [CostPocket.USER_KEY]


async def test_a_tenant_with_no_key_of_their_own_does_not_spend_the_platform_s() -> None:
    """The other half of BYOK, and the one that costs real money if it is wrong.

    Before this task a Live compile always read the process environment, so *every* tenant's map
    was built on the platform's key. What is asserted here is only the pocket the spend lands in;
    that an unkeyed tenant then routes to the keyless local model is ``build_chat_model``'s
    behaviour, proved in its own suite — this double has no such routing to exercise.
    """

    # Arrange — a tenant who has set no keys at all: the vault answers with an empty map, which is
    # NOT the same as BYOK being off (that is a `None` resolver, and reads the environment).
    async def resolve(user_id: str) -> dict[str, str]:
        return {}

    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = LiveGraphService(
        SpendingCompiler(),  # type: ignore[arg-type]
        MemoryGraphStore(),
        cost_event_store=ledger,
        subject_cost_store=rollup,
        credential_resolver=resolve,
    )

    # Act
    graph = await service.compile("Tides", run_id="r1", owner_id="alice")

    # Assert — no key of theirs was in play, so the spend is the platform's and says so.
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=graph.graph_id, owner_id="alice"
    )
    assert [e.pocket for e in events] == [CostPocket.PLATFORM]


async def test_a_compile_with_metering_unwired_still_compiles() -> None:
    """Metering is observability, never part of the compile's success contract — and the keyless /
    offline path runs with no stores at all."""
    # Arrange
    service = LiveGraphService(SpendingCompiler(), MemoryGraphStore())  # type: ignore[arg-type]

    # Act
    graph = await service.compile("Tides", run_id="r1", owner_id=None)

    # Assert
    assert graph.topic == "Tides"


def test_the_composition_root_wires_metering_and_byok_into_the_service(tmp_path: Path) -> None:
    """Without this, production could stop metering Live entirely and every test above would still
    pass — they construct the service themselves. This is the one that watches the wiring.

    Asserted on the injected collaborators rather than through a compile, because the offline
    pipeline this runs under is the stub compiler, which spends nothing: a behavioural probe here
    would be green whether or not the stores were connected.
    """
    # Arrange
    from lunaris_api.config import Settings
    from lunaris_api.live.dependencies import get_live_graph_service

    # A real master key, because that is what turns BYOK on: with the default (None) the resolver
    # is None whether or not the composition root wires it, so the assertion below would hold even
    # if the wiring were deleted — the exact false pass this test exists to prevent.
    settings = Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        key_enc_master=_MASTER_KEY_B64,
    )
    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()

    # Act
    service = get_live_graph_service(settings, ledger, rollup)

    # Assert — the same stores Studio's builds write to, so one tenant has one ledger...
    assert service._cost_event_store is ledger
    assert service._subject_cost_store is rollup
    # ...and the tenant's own keys reach the compiler. Without this, BYOK could be dropped from the
    # wiring and every tenant would silently go back to spending the platform's key.
    assert service._credential_resolver is not None


async def test_a_slow_ledger_cannot_hold_a_learner_past_the_pause() -> None:
    """C1's budget is the wall clock a learner waits, not the thinking inside it.

    The drain is store I/O that happens after the answer exists, so a degraded ledger would
    otherwise extend the request by however long the store takes to give up — turning a pause a
    tutor can talk over into one they cannot. Losing the telemetry is the cheaper failure.
    """

    # Arrange — a ledger that never answers.
    class HangingLedger(InMemoryCostEventStore):
        async def append(self, *, events, owner_id=None):  # type: ignore[override]
            await asyncio.sleep(30)

    service = LiveGraphService(
        SpendingCompiler(),  # type: ignore[arg-type]
        MemoryGraphStore(),
        cost_event_store=HangingLedger(),
        subject_cost_store=InMemorySubjectCostStore(),
        extend_deadline_s=1.0,
    )

    # Act — bounded well under the 30s the ledger would take.
    graph = await asyncio.wait_for(
        service.compile("Tides", run_id="r1", owner_id="alice"), timeout=5
    )

    # Assert — the map is still returned; only the ledger row was lost.
    assert graph.topic == "Tides"


async def test_resolving_a_tenant_s_keys_counts_against_the_pause() -> None:
    """A vault lookup is a network round trip per configured provider. Left outside the deadline it
    is time the budget does not bound — the same defect T5 fixed here for the store load and save,
    which is exactly why this is pinned rather than trusted."""

    # Arrange — a vault that hangs, and an extension budget of one second.
    async def hanging_resolver(user_id: str) -> dict[str, str]:
        await asyncio.sleep(30)
        return {}

    service = LiveGraphService(
        SpendingCompiler(),  # type: ignore[arg-type]
        MemoryGraphStore(),
        credential_resolver=hanging_resolver,
        extend_deadline_s=1.0,
    )

    # Act — the outer bound is only a backstop so a regression fails the suite instead of hanging
    # it; what is asserted is that the SERVICE's own deadline is what fired.
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            service.extend(
                "g1", request="what about momentum?", anchors=[], run_id="r2", owner_id="alice"
            ),
            timeout=10,
        )
    elapsed = time.monotonic() - started

    # Assert — refused at the extension's own 1-second budget, not at the backstop. Without this
    # the test passes either way: a TimeoutError is a TimeoutError whichever clock raised it.
    assert elapsed < 5, "the vault call was not bounded by the extension's budget"


async def test_two_owners_compile_on_their_own_keys() -> None:
    """One tenant's key must never build another tenant's map.

    Structural, not incidental: ``ClaudeGraphCompiler`` bakes the resolved key into its chat model
    on first use and caches it, so a compiler shared between requests would serve every later
    tenant on the first one's key. Nothing today caches it — but nearly every sibling getter in the
    composition root *is* ``@lru_cache``d, so the invariant is one plausible edit away from
    breaking, and this is what would notice.
    """
    # Arrange — a compiler that records whose key was in scope when it ran.
    seen: list[str | None] = []

    class KeyWatchingCompiler(SpendingCompiler):
        async def compile(self, topic: str, *, graph_id: str, run_id: str, **kwargs: object):
            seen.append(resolve_secret("ANTHROPIC_API_KEY"))
            return await super().compile(topic, graph_id=graph_id, run_id=run_id, **kwargs)

    async def resolve(user_id: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": f"key-for-{user_id}"}

    def _for(owner: str) -> LiveGraphService:
        # A fresh service per request, exactly as the composition root builds one.
        return LiveGraphService(
            KeyWatchingCompiler(),  # type: ignore[arg-type]
            MemoryGraphStore(),
            credential_resolver=resolve,
        )

    # Act
    await _for("alice").compile("Tides", run_id="r1", owner_id="alice")
    await _for("bob").compile("Gravity", run_id="r2", owner_id="bob")

    # Assert
    assert seen == ["key-for-alice", "key-for-bob"]
