"""P7.2-T1 — the live standard researcher: query building, tolerant distillation parsing, and the
search → fetch → distil orchestration that grounds a brief in real competencies with provenance.

The researcher is a hybrid moat (deterministic search/fetch + one LLM distillation call), tested
fully offline: a stub search provider + stub content extractor feed canned pages, and a fake chat
model returns the canned distillation JSON, so the orchestration — provenance assembly, the
COMPLETE/PARTIAL/UNAVAILABLE status, honest degradation — is proven without a key or the network.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from lunaris_agent.subagents.standard_researcher import (
    ClaudeStandardResearcher,
    build_research_queries,
    parse_distillation,
    parse_research,
)
from lunaris_grounding import (
    ExtractedContent,
    ResearchBudget,
    SearchResult,
    StubContentExtractor,
    StubSearchProvider,
    research_budget_for_brief,
)
from lunaris_runtime.schema import (
    CompetencyArea,
    CourseBrief,
    Gap,
    GapMagnitude,
    GoalType,
    Level,
    ResearchStatus,
    StandardKind,
    StandardResearch,
    TargetStandard,
    TrustTier,
)

_FIXED_CLOCK = "2026-06-03T12:00:00Z"


def _clb_brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across all four skills",
        target_standard=TargetStandard(
            name="CLB 10", kind=StandardKind.EXTERNAL_STANDARD, authority_hint="ircc.canada.ca"
        ),
        target_level=Level.ADVANCED,
        needs_research=True,
    )


def _demanding_clb_brief() -> CourseBrief:
    """The CLB brief as a demanding credential goal (CQ Phase 1.2), keeping the same named standard
    so the deterministic first query is unchanged across the two CLB fixtures."""
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across all four skills",
        goal_type=GoalType.CREDENTIAL,
        target_standard=TargetStandard(
            name="CLB 10", kind=StandardKind.EXTERNAL_STANDARD, authority_hint="ircc.canada.ca"
        ),
        target_level=Level.EXPERT,
        gap=Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.LARGE),
        needs_research=True,
    )


def _model(json_text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=json_text)]))


class _DistillationMustNotBeCalled:
    """A chat-model double that fails the test if distillation runs — proves the no-source path
    short-circuits before the LLM call (clearer than relying on an empty iterator raising)."""

    async def ainvoke(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("distillation must not run when no source is fetchable")


class _RaisingSearchProvider:
    """A search provider that always raises — to prove the researcher absorbs a flaky backend."""

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise RuntimeError("search backend is down")


class _ExtractorMustNotFetch:
    """Raises if asked to fetch — proves a blocked URL is dropped before any fetch."""

    async def extract(self, url: str) -> ExtractedContent | None:
        raise AssertionError(f"a blocked domain must never be fetched: {url}")


def _two_source_researcher(model: object) -> ClaudeStandardResearcher:
    """A researcher over two canned, fetchable CLB sources — the happy-path acquisition fixture."""
    search = StubSearchProvider(
        [
            SearchResult(url="https://ircc.canada.ca/clb10", title="CLB 10 — IRCC"),
            SearchResult(url="https://example.edu/clb-guide", title="CLB guide"),
        ]
    )
    extractor = StubContentExtractor(
        {
            "https://ircc.canada.ca/clb10": ExtractedContent(
                url="https://ircc.canada.ca/clb10",
                text="CLB 10 listeners infer implied intent and hedged disagreement.",
                title="CLB 10 — IRCC",
            ),
            "https://example.edu/clb-guide": ExtractedContent(
                url="https://example.edu/clb-guide",
                text="At CLB 10 a reader tracks authorial stance and subtext.",
                title="CLB guide",
            ),
        }
    )
    return ClaudeStandardResearcher(model, search, extractor, clock=lambda: _FIXED_CLOCK)


# ---- the deterministic query builder -------------------------------------------------------------


def test_build_research_queries_targets_the_named_standard_and_its_authority() -> None:
    # Arrange
    brief = _clb_brief()

    # Act
    queries = build_research_queries(brief)

    # Assert — narrow queries for what the level MEANS + how it's measured, plus an authority-biased
    # query (Claude's "what it means" + "how it's measured" split, grounded against the real body).
    assert any("CLB 10" in q and "competenc" in q.lower() for q in queries)
    assert any("CLB 10" in q and "level" in q.lower() for q in queries)
    assert any("ircc.canada.ca" in q for q in queries)


def test_build_research_queries_falls_back_to_goal_and_subject_without_a_standard() -> None:
    # Arrange — a goal with no externally-named standard (informal target).
    brief = CourseBrief(
        subject="Distributed systems",
        goal="master distributed consensus",
        target_level=Level.EXPERT,
    )

    # Act
    queries = build_research_queries(brief)

    # Assert — queries derive from the goal + subject + level, never empty.
    assert queries
    assert any("distributed consensus" in q for q in queries)
    assert any("Distributed systems" in q for q in queries)


# ---- the tolerant distillation parser ------------------------------------------------------------


def test_parse_research_reads_competencies_and_score_table_from_prose_wrapped_json() -> None:
    # Arrange
    text = (
        "Here is what the sources say:\n"
        '{"competencies": ["hear implied intent", "read authorial stance"], '
        '"score_table": ["CELPIP 10", "IELTS 8.5"]}\nThat is the distillation.'
    )

    # Act
    competencies, score_table = parse_research(text)

    # Assert
    assert competencies == ["hear implied intent", "read authorial stance"]
    assert score_table == ["CELPIP 10", "IELTS 8.5"]


def test_parse_research_degrades_to_empty_on_garbage_rather_than_raising() -> None:
    # Research is best-effort: a model that returns no JSON must NOT crash the build.
    assert parse_research("I could not find anything useful.") == ([], [])
    # Non-string list items are coerced/stripped; blanks dropped.
    competencies, _score = parse_research('{"competencies": ["  keep  ", "", 42]}')
    assert competencies == ["keep", "42"]


# ---- the structured competency framework (CQ Phase 1.1) ------------------------------------------


def test_parse_distillation_reads_structured_competency_areas() -> None:
    # Arrange — the adaptive distil returns a framework: named areas, each with descriptors, plus
    # follow-up queries for thin areas (CQ Phase 1.1).
    text = (
        '{"areas": ['
        '{"name": "Listening", "competencies": ["infer implied intent", "track stance"]},'
        '{"name": "Writing", "competencies": ["sustain a formal register"]}],'
        '"score_table": ["CELPIP 10"], "follow_up_queries": ["CLB 10 speaking descriptors"]}'
    )

    # Act
    distillation = parse_distillation(text)

    # Assert — areas carry their descriptors; competencies is the flattened view; follow-ups parsed.
    assert [area.name for area in distillation.areas] == ["Listening", "Writing"]
    assert distillation.areas[0].competencies == ["infer implied intent", "track stance"]
    assert distillation.competencies == [
        "infer implied intent",
        "track stance",
        "sustain a formal register",
    ]
    assert distillation.score_table == ["CELPIP 10"]
    assert distillation.follow_up_queries == ["CLB 10 speaking descriptors"]


def test_parse_distillation_falls_back_to_flat_competencies() -> None:
    # Arrange — an older/flat response with no areas. The parser keeps the flat competencies so the
    # researcher still grounds (back-compat with the pre-framework shape).
    text = '{"competencies": ["hear implied intent", "read stance"], "score_table": []}'

    # Act
    distillation = parse_distillation(text)

    # Assert
    assert distillation.areas == []
    assert distillation.competencies == ["hear implied intent", "read stance"]
    assert distillation.follow_up_queries == []


def test_standard_research_derives_flat_competencies_from_areas() -> None:
    # Arrange — a framework with only areas; a repeated descriptor exercises dedup/order-preserving.
    areas = [
        CompetencyArea(name="Listening", competencies=["infer intent", "track stance"]),
        CompetencyArea(name="Listening dup", competencies=["infer intent"]),
    ]

    # Act
    research = StandardResearch(status=ResearchStatus.PARTIAL, areas=areas)

    # Assert — the validator flattens areas into competencies for the flat consumers
    # (extractor/curriculum) until they read areas directly.
    assert research.competencies == ["infer intent", "track stance"]


def test_grounding_outline_renders_areas_with_descriptors() -> None:
    # Arrange — a structured framework (CQ Phase 1.3).
    research = StandardResearch(
        status=ResearchStatus.PARTIAL,
        areas=[CompetencyArea(name="Listening", competencies=["infer intent", "track stance"])],
    )

    # Act
    outline = research.grounding_outline()

    # Assert — an area-headed line with its descriptors joined (the separator is part of the shape).
    assert "Listening: infer intent; track stance" in outline


def test_grounding_outline_falls_back_to_flat_competencies() -> None:
    # Arrange — no areas, only a flat competency list.
    research = StandardResearch(status=ResearchStatus.PARTIAL, competencies=["c1", "c2"])

    # Act
    outline = research.grounding_outline()

    # Assert
    assert "c1" in outline
    assert "c2" in outline


# ---- the search → fetch → distil orchestration ---------------------------------------------------


async def test_researcher_distills_competencies_with_provenance() -> None:
    # Arrange — two fetchable sources and a model that distils two competencies + a score.
    researcher = _two_source_researcher(
        _model(
            '{"competencies": ["hear implied intent in speech", "read authorial stance"], '
            '"score_table": ["CELPIP 10"]}'
        )
    )

    # Act
    outcome = await researcher.research(_clb_brief())
    research = outcome.research

    # Assert — grounded: competencies + score table distilled, status COMPLETE, and every source
    # (deduped across the three queries) carries structural provenance, stamped at acquisition.
    assert research.status is ResearchStatus.COMPLETE
    assert "hear implied intent in speech" in research.competencies
    assert research.score_table == ["CELPIP 10"]
    urls = {source.url for source in research.sources}
    assert urls == {"https://ircc.canada.ca/clb10", "https://example.edu/clb-guide"}
    assert all(source.fetched_at == _FIXED_CLOCK for source in research.sources)
    # Each source carries its real, classified trust tier: the standard's own body is OFFICIAL,
    # the university guide REPUTABLE (the authority hint comes from the brief's target_standard).
    tiers = {source.url: source.trust_tier for source in research.sources}
    assert tiers["https://ircc.canada.ca/clb10"] is TrustTier.OFFICIAL
    assert tiers["https://example.edu/clb-guide"] is TrustTier.REPUTABLE
    # The same fetched pages are carried as corpus seeds (P6.4) — one per fetched source, with the
    # extracted text and acquisition-time provenance, so the SEED feed ingests them without
    # re-fetching. Credibility is left unset on purpose (the ingestor's scorer grades each seed).
    assert {seed.url for seed in outcome.seeds} == urls
    assert all(seed.text for seed in outcome.seeds)
    assert all(seed.fetched_at == _FIXED_CLOCK for seed in outcome.seeds)
    seed_tiers = {seed.url: seed.trust_tier for seed in outcome.seeds}
    assert seed_tiers["https://ircc.canada.ca/clb10"] is TrustTier.OFFICIAL


async def test_researcher_is_unavailable_when_no_source_can_be_fetched() -> None:
    # Arrange — search returns a hit, but the fetch fails (extractor returns None); the model double
    # would fail the test if invoked, proving distillation is skipped when there's nothing to read.
    search = StubSearchProvider([SearchResult(url="https://unreachable.example/clb")])
    researcher = ClaudeStandardResearcher(
        _DistillationMustNotBeCalled(), search, StubContentExtractor(), clock=lambda: _FIXED_CLOCK
    )

    # Act
    outcome = await researcher.research(_clb_brief())
    research = outcome.research

    # Assert — honest degradation: UNAVAILABLE, no fabricated sources or competencies, and no seeds
    # (nothing was fetched, so the SEED feed has nothing to ingest).
    assert research.status is ResearchStatus.UNAVAILABLE
    assert research.sources == []
    assert research.competencies == []
    assert outcome.seeds == ()


async def test_researcher_is_unavailable_when_the_search_backend_raises() -> None:
    # Arrange — the search backend throws; best-effort degradation must absorb it, never crash.
    researcher = ClaudeStandardResearcher(
        _DistillationMustNotBeCalled(),
        _RaisingSearchProvider(),
        StubContentExtractor(),
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — a flaky provider degrades to UNAVAILABLE rather than aborting the build.
    assert research.status is ResearchStatus.UNAVAILABLE
    assert research.sources == []


async def test_researcher_is_partial_when_sources_read_but_nothing_distils() -> None:
    # Arrange — a source is fetched, but the model distils no competencies from it.
    search = StubSearchProvider([SearchResult(url="https://example.edu/thin", title="Thin")])
    extractor = StubContentExtractor(
        {"https://example.edu/thin": ExtractedContent(url="https://example.edu/thin", text="...")}
    )
    researcher = ClaudeStandardResearcher(
        _model('{"competencies": [], "score_table": []}'),
        search,
        extractor,
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — sources were reached but grounding was thin: PARTIAL, with the source still cited and
    # carrying its provenance (the clock injection stamps the non-COMPLETE branch too).
    assert research.status is ResearchStatus.PARTIAL
    assert research.competencies == []
    assert len(research.sources) == 1
    assert research.sources[0].url == "https://example.edu/thin"
    assert research.sources[0].fetched_at == _FIXED_CLOCK
    assert research.sources[0].trust_tier is TrustTier.REPUTABLE


# ---- trust-tier preference + the per-build budget (T2) ------------------------------------------


async def test_researcher_prefers_higher_trust_tiers_within_the_fetch_budget() -> None:
    # Arrange — four candidates of mixed tiers but a budget that fetches only two: the researcher
    # keeps the two highest-trust sources (official first, then reputable) and drops the open ones.
    urls = [
        "https://blog.example.com/clb",  # OPEN
        "https://ircc.canada.ca/clb",  # OFFICIAL (the brief's authority body)
        "https://news.example.org/clb",  # OPEN
        "https://uni.edu/clb",  # REPUTABLE
    ]
    search = StubSearchProvider([SearchResult(url=url) for url in urls])
    extractor = StubContentExtractor(
        {url: ExtractedContent(url=url, text="CLB content") for url in urls}
    )
    researcher = ClaudeStandardResearcher(
        _model('{"competencies": ["c"], "score_table": []}'),
        search,
        extractor,
        budget=ResearchBudget(max_searches=3, max_fetches=2),
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — the two top-tier sources, official ahead of reputable; the open ones were DROPPED
    # by the budget (not merely sorted to the back), so no unfetched source is ever cited.
    assert [source.url for source in research.sources] == [
        "https://ircc.canada.ca/clb",
        "https://uni.edu/clb",
    ]
    assert [source.trust_tier for source in research.sources] == [
        TrustTier.OFFICIAL,
        TrustTier.REPUTABLE,
    ]
    kept = {source.url for source in research.sources}
    assert "https://blog.example.com/clb" not in kept
    assert "https://news.example.org/clb" not in kept
    assert all(source.trust_tier is not TrustTier.OPEN for source in research.sources)


async def test_researcher_never_fetches_a_blocked_domain() -> None:
    # Arrange — the only hit is a blocked shortener; it must never be fetched (so → UNAVAILABLE).
    search = StubSearchProvider([SearchResult(url="https://bit.ly/clb")])
    researcher = ClaudeStandardResearcher(
        _DistillationMustNotBeCalled(),
        search,
        _ExtractorMustNotFetch(),
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — the blocked domain yielded nothing fetchable; honest UNAVAILABLE.
    assert research.status is ResearchStatus.UNAVAILABLE
    assert research.sources == []


async def test_research_budget_caps_the_number_of_fetched_sources() -> None:
    # Arrange — three fetchable reputable sources, but a budget of a single fetch.
    urls = ["https://a.edu/x", "https://b.edu/x", "https://c.edu/x"]
    search = StubSearchProvider([SearchResult(url=url) for url in urls])
    extractor = StubContentExtractor(
        {url: ExtractedContent(url=url, text="content") for url in urls}
    )
    researcher = ClaudeStandardResearcher(
        _model('{"competencies": ["c"], "score_table": []}'),
        search,
        extractor,
        budget=ResearchBudget(max_searches=2, max_fetches=1),
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — exactly the first reputable source survives despite three being available; the budget
    # bounds the work and the result is still grounded (COMPLETE) on that one source.
    assert research.status is ResearchStatus.COMPLETE
    assert [source.url for source in research.sources] == ["https://a.edu/x"]
    assert research.sources[0].trust_tier is TrustTier.REPUTABLE


# ---- the depth policy: budget sized to the brief (CQ Phase 1.2) ----------------------------------


def test_research_budget_policy_scales_up_for_a_demanding_goal() -> None:
    # Arrange — a credential goal at the ceiling with a large gap should earn deeper research than a
    # casual knowledge intro, keyed off the brief abstractions (never the topic).
    demanding = CourseBrief(
        subject="AWS",
        goal="Pass the AWS Solutions Architect exam",
        goal_type=GoalType.CREDENTIAL,
        target_level=Level.EXPERT,
        gap=Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.LARGE),
    )
    casual = CourseBrief(
        subject="Houseplants",
        goal="Understand how to keep houseplants alive",
        goal_type=GoalType.KNOWLEDGE,
        target_level=Level.NOVICE,
        gap=Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.SMALL),
    )

    # Act
    deep = research_budget_for_brief(demanding)
    shallow = research_budget_for_brief(casual)

    # Assert — every dimension is at least as large for the demanding goal, and strictly deeper
    # overall (more rounds), so depth tracks the goal rather than being a fixed 3/4 for everyone.
    assert deep.max_searches > shallow.max_searches
    assert deep.max_fetches > shallow.max_fetches
    assert deep.max_rounds > shallow.max_rounds
    assert shallow.max_rounds >= 1  # a casual goal still researches once


def test_research_budget_policy_isolates_the_goal_type_axis() -> None:
    # Arrange — two briefs identical except goal_type (skill vs knowledge), so any depth difference
    # is attributable to that axis alone (the scaling test moves all three axes at once).
    base = {"subject": "s", "goal": "g", "target_level": Level.NOVICE}
    skill = CourseBrief(**base, goal_type=GoalType.SKILL)
    knowledge = CourseBrief(**base, goal_type=GoalType.KNOWLEDGE)

    # Act
    skill_budget = research_budget_for_brief(skill)
    knowledge_budget = research_budget_for_brief(knowledge)

    # Assert — goal_type alone deepens the budget.
    assert skill_budget.max_searches > knowledge_budget.max_searches


def test_research_budget_policy_is_a_valid_budget() -> None:
    # Arrange — the deepest possible brief (every axis at its ceiling).
    brief = CourseBrief(
        subject="s",
        goal="g",
        goal_type=GoalType.CREDENTIAL,
        target_level=Level.EXPERT,
        gap=Gap(magnitude=GapMagnitude.LARGE),
    )

    # Act — the policy must emit a budget the ResearchBudget guards accept (no raise).
    budget = research_budget_for_brief(brief)

    # Assert
    assert budget.max_searches >= 3
    assert budget.max_rounds >= 2


async def test_researcher_with_no_explicit_budget_uses_the_brief_policy() -> None:
    # Arrange — no explicit budget, so the researcher must size itself from the brief. A demanding
    # credential brief earns >=2 rounds, so the follow-up round runs and the deeper page is fetched.
    model = _scripted_model(
        [
            '{"areas": [{"name": "Listening", "competencies": ["infer intent"]}],'
            f' "score_table": [], "follow_up_queries": ["{_FOLLOW_UP}"]}}',
            '{"areas": [{"name": "Listening", "competencies": ["infer intent"]},'
            '{"name": "Speaking", "competencies": ["sustain a turn"]}],'
            '"score_table": [], "follow_up_queries": []}',
        ]
    )
    # None budget → the researcher must size itself from the brief; the demanding CLB credential
    # brief is a credential at the ceiling, so the policy grants the deepening round.
    researcher = _deepening_fixture(model, budget=None)

    # Act
    research = (await researcher.research(_demanding_clb_brief())).research

    # Assert — the policy-sized budget let the loop deepen onto the speaking page.
    assert [area.name for area in research.areas] == ["Listening", "Speaking"]


# ---- the adaptive deepening loop (CQ Phase 1.1) --------------------------------------------------


class _QueryKeyedSearch:
    """A search provider whose results depend on the query — so a deeper follow-up query can surface
    a page the first-round queries did not, exercising the adaptive loop."""

    def __init__(self, by_query: dict[str, list[SearchResult]]) -> None:
        self._by_query = by_query

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._by_query.get(query, [])


def _scripted_model(messages: list[str]) -> GenericFakeChatModel:
    msgs: list[BaseMessage] = [AIMessage(content=text) for text in messages]
    return GenericFakeChatModel(messages=iter(msgs))


_FIRST_QUERY = build_research_queries(_clb_brief())[0]  # the round-1 query the fixture keys on
_FOLLOW_UP = "CLB 10 speaking descriptors"


def _deepening_fixture(model: object, *, budget: ResearchBudget | None) -> ClaudeStandardResearcher:
    """Round 1's queries surface a shallow listening page; the model's follow-up query surfaces a
    deeper speaking page. The loop fetches the second page only if it runs the follow-up round."""
    shallow = "https://ircc.canada.ca/clb10-listening"
    deep = "https://ircc.canada.ca/clb10-speaking"
    search = _QueryKeyedSearch(
        {
            _FIRST_QUERY: [SearchResult(url=shallow, title="CLB 10 listening")],
            _FOLLOW_UP: [SearchResult(url=deep, title="CLB 10 speaking")],
        }
    )
    extractor = StubContentExtractor(
        {
            shallow: ExtractedContent(url=shallow, text="CLB 10 listening descriptors.", title="L"),
            deep: ExtractedContent(url=deep, text="CLB 10 speaking descriptors.", title="S"),
        }
    )
    return ClaudeStandardResearcher(
        model, search, extractor, budget=budget, clock=lambda: _FIXED_CLOCK
    )


async def test_researcher_deepens_on_follow_up_queries_within_budget() -> None:
    # Arrange — round 1 distils a thin listening area + proposes a follow-up query; round 2 then
    # distils a richer two-area framework once the deeper speaking page is fetched.
    model = _scripted_model(
        [
            '{"areas": [{"name": "Listening", "competencies": ["infer intent"]}],'
            f' "score_table": [], "follow_up_queries": ["{_FOLLOW_UP}"]}}',
            '{"areas": [{"name": "Listening", "competencies": ["infer intent"]},'
            '{"name": "Speaking", "competencies": ["sustain a turn"]}],'
            '"score_table": [], "follow_up_queries": []}',
        ]
    )
    researcher = _deepening_fixture(model, budget=ResearchBudget(max_searches=6, max_fetches=6))

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — the loop ran the follow-up query, fetched the deeper page, and the final framework
    # covers both areas with provenance from both rounds.
    assert research.status is ResearchStatus.COMPLETE
    assert [area.name for area in research.areas] == ["Listening", "Speaking"]
    assert "sustain a turn" in research.competencies
    urls = {source.url for source in research.sources}
    assert "https://ircc.canada.ca/clb10-speaking" in urls


async def test_research_max_rounds_one_does_not_deepen() -> None:
    # Arrange — same follow-up signal, but a single-round budget: the deeper page must never be
    # fetched, proving max_rounds bounds the adaptive loop (the cost ceiling CQ Phase 1.2 sizes).
    model = _scripted_model(
        [
            '{"areas": [{"name": "Listening", "competencies": ["infer intent"]}],'
            f' "score_table": [], "follow_up_queries": ["{_FOLLOW_UP}"]}}',
        ]
    )
    researcher = _deepening_fixture(
        model, budget=ResearchBudget(max_searches=6, max_fetches=6, max_rounds=1)
    )

    # Act
    research = (await researcher.research(_clb_brief())).research

    # Assert — only the first-round page; the follow-up round never ran.
    assert [area.name for area in research.areas] == ["Listening"]
    urls = {source.url for source in research.sources}
    assert "https://ircc.canada.ca/clb10-speaking" not in urls
