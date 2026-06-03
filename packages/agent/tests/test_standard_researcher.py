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
    research = await researcher.research(_clb_brief())

    # Assert — grounded: competencies + score table distilled, status COMPLETE, and every source
    # (deduped across the three queries) carries structural provenance, stamped at acquisition.
    assert research.status is ResearchStatus.COMPLETE
    assert "hear implied intent in speech" in research.competencies
    assert research.score_table == ["CELPIP 10"]
    urls = {source.url for source in research.sources}
    assert urls == {"https://ircc.canada.ca/clb10", "https://example.edu/clb-guide"}
    assert all(source.fetched_at == _FIXED_CLOCK for source in research.sources)
    assert all(source.trust_tier is TrustTier.OPEN for source in research.sources)


async def test_researcher_is_unavailable_when_no_source_can_be_fetched() -> None:
    # Arrange — search returns a hit, but the fetch fails (extractor returns None); the model double
    # would fail the test if invoked, proving distillation is skipped when there's nothing to read.
    search = StubSearchProvider([SearchResult(url="https://unreachable.example/clb")])
    researcher = ClaudeStandardResearcher(
        _DistillationMustNotBeCalled(), search, StubContentExtractor(), clock=lambda: _FIXED_CLOCK
    )

    # Act
    research = await researcher.research(_clb_brief())

    # Assert — honest degradation: UNAVAILABLE, no fabricated sources or competencies.
    assert research.status is ResearchStatus.UNAVAILABLE
    assert research.sources == []
    assert research.competencies == []


async def test_researcher_is_unavailable_when_the_search_backend_raises() -> None:
    # Arrange — the search backend throws; best-effort degradation must absorb it, never crash.
    researcher = ClaudeStandardResearcher(
        _DistillationMustNotBeCalled(),
        _RaisingSearchProvider(),
        StubContentExtractor(),
        clock=lambda: _FIXED_CLOCK,
    )

    # Act
    research = await researcher.research(_clb_brief())

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
    research = await researcher.research(_clb_brief())

    # Assert — sources were reached but grounding was thin: PARTIAL, with the source still cited and
    # carrying its provenance (the clock injection stamps the non-COMPLETE branch too).
    assert research.status is ResearchStatus.PARTIAL
    assert research.competencies == []
    assert len(research.sources) == 1
    assert research.sources[0].url == "https://example.edu/thin"
    assert research.sources[0].fetched_at == _FIXED_CLOCK
    assert research.sources[0].trust_tier is TrustTier.OPEN
