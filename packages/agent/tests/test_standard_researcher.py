"""P7.2-T1 — the live standard researcher: query building, tolerant distillation parsing, and the
search → fetch → distil orchestration that grounds a brief in real competencies with provenance.

The researcher is a hybrid moat (deterministic search/fetch + one LLM distillation call), tested
fully offline: a stub search provider + stub content extractor feed canned pages, and a fake chat
model returns the canned distillation JSON, so the orchestration — provenance assembly, the
COMPLETE/PARTIAL/UNAVAILABLE status, honest degradation — is proven without a key or the network.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from lunaris_agent.subagents.standard_researcher import (
    ClaudeStandardResearcher,
    build_research_queries,
    parse_research,
)
from lunaris_grounding import (
    ExtractedContent,
    ResearchBudget,
    SearchResult,
    StubContentExtractor,
    StubSearchProvider,
)
from lunaris_runtime.schema import (
    CourseBrief,
    Level,
    ResearchStatus,
    StandardKind,
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
