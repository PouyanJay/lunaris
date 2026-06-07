"""P7.4-T1 — the live resource curator's deterministic moat (no model, no network).

The relevance judgement is the model's job, proven end-to-end by the live eval; here we prove the
parts that DON'T need a live model: the per-kind query plan, the tolerant judge parser, and that
``ClaudeResourceCurator`` searches → classifies trust deterministically → asks the judge (BLIND to
the trust tier, §15) → attaches the kept resources to the chosen phases with provenance stamped at
selection. Search + video + the judge are all stubbed/injected so the run is offline + repeatable.
"""

from langchain_core.messages import AIMessage
from lunaris_agent.subagents.resource_curator import (
    ClaudeResourceCurator,
    SearchQuery,
    build_curation_prompt,
    build_resource_queries,
)
from lunaris_agent.subagents.resource_curator.candidate_view import CandidateView
from lunaris_agent.subagents.resource_curator.parser import parse_curation
from lunaris_grounding import (
    ResourceBudget,
    SearchResult,
    StubSearchProvider,
    StubVideoSource,
    VideoResult,
)
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    Level,
    Module,
    Objective,
    ResourceKind,
    TrustTier,
)


class _RecordingSearch:
    """An ISearchProvider that records the max_results asked for and replays fixed results."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.max_results: list[int] = []

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.max_results.append(max_results)
        return self._results


class _OneQueryTranslator:
    """A translator that emits one SearchQuery carrying the judge content signal (for T2 tests)."""

    def __init__(self, query: SearchQuery) -> None:
        self._query = query

    async def translate(self, module, brief=None, *, modality=None, feedback=None):
        return [self._query]


class _FeedbackAwareTranslator:
    """Records the feedback of each translate call (for the T5 broaden-retry test)."""

    def __init__(self, query: SearchQuery) -> None:
        self._query = query
        self.feedbacks: list[str | None] = []

    async def translate(self, module, brief=None, *, modality=None, feedback=None):
        self.feedbacks.append(feedback)
        return [self._query]


class _EmptyOnFirstPassSearch:
    """Returns nothing on the first query, then results once the broaden-retry runs (T5)."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.calls = 0

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls += 1
        return [] if self.calls == 1 else self._results


class _FakeJudge:
    """A chat model stand-in: records each prompt it receives and replays a fixed JSON response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._response)


def _module() -> Module:
    return Module(
        id="m0",
        title="Listening for intent",
        kcs=["intent"],
        competency="hear implied intent in speech",
        objectives=[
            Objective(
                statement="Given audio, the learner can analyze implied intent.",
                bloom_level=BloomLevel.ANALYZE,
                kc="intent",
            )
        ],
        difficulty_index=0.6,
    )


def _brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency", goal="reach CLB 10", target_level=Level.ADVANCED
    )


def test_build_resource_queries_anchors_on_competency_and_tags_each_kind() -> None:
    # Arrange / Act
    queries = build_resource_queries(_module(), _brief())

    # Assert — one query per sourced kind (video routes to the IVideoSource, the rest to search),
    # each anchored on the researched competency.
    kinds = {kind for kind, _query in queries}
    assert kinds == {
        ResourceKind.VIDEO,
        ResourceKind.ARTICLE,
        ResourceKind.PRACTICE,
        ResourceKind.DOCS,
    }
    assert all("hear implied intent in speech" in query for _kind, query in queries)


def test_parse_curation_reads_selections_and_tolerates_junk() -> None:
    # Arrange — a valid pick, a bad-phase pick (→ demonstrate), and one with no index (dropped).
    text = """noise {"selected": [
      {"index": 0, "phase": "apply", "why": "drills", "credibility": 0.7},
      {"index": 1, "phase": "bogus", "why": "x", "credibility": 5},
      {"phase": "apply", "why": "no index"}
    ]} trailing"""

    # Act
    choices = parse_curation(text)

    # Assert — the index-less entry is dropped; a bad phase falls back; credibility is clamped to 1.
    assert [c.index for c in choices] == [0, 1]
    assert choices[0].phase == "apply"
    assert choices[1].phase == "demonstrate"
    assert choices[1].credibility == 1.0


async def test_curate_judges_blind_to_trust_and_stamps_provenance() -> None:
    # Arrange — a video candidate (open web) + an article candidate (academic → REPUTABLE); the
    # judge keeps both, placing the video on demonstrate and the article on apply.
    video = VideoResult(
        url="https://www.youtube.com/watch?v=xyz",
        title="Implied intent, decoded",
        channel="EnglishPro",
        duration="10:00",
    )
    article = SearchResult(url="https://ling.example.edu/stance", title="Reading authorial stance")
    judge = _FakeJudge(
        '{"selected": ['
        '{"index": 0, "phase": "demonstrate", "why": "Worked example of decoding intent.", '
        '"credibility": 0.85},'
        '{"index": 1, "phase": "apply", "why": "Stance-reading drills.", "credibility": 0.7}]}'
    )
    curator = ClaudeResourceCurator(
        judge,
        StubSearchProvider([article]),
        StubVideoSource([video]),
        clock=lambda: "2026-06-03T12:00:00Z",
    )

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — the video landed on demonstrate with its identity, metadata + judge fields.
    assert len(curated.demonstrate) == 1
    vid = curated.demonstrate[0]
    assert vid.kind is ResourceKind.VIDEO
    assert vid.url == "https://www.youtube.com/watch?v=xyz"
    assert vid.title == "Implied intent, decoded"
    assert vid.source == "youtube.com"
    assert vid.trust_tier is TrustTier.OPEN  # classified deterministically, not by the judge
    assert vid.credibility == 0.85
    assert vid.why == "Worked example of decoding intent."
    assert vid.fetched_at == "2026-06-03T12:00:00Z"
    assert vid.duration == "10:00"
    assert vid.author == "EnglishPro"

    # The article landed on apply, classified REPUTABLE from its academic domain, with judge fields.
    assert len(curated.apply) == 1
    article_resource = curated.apply[0]
    assert article_resource.kind is ResourceKind.ARTICLE
    assert article_resource.trust_tier is TrustTier.REPUTABLE
    assert article_resource.credibility == 0.7
    assert article_resource.why == "Stance-reading drills."

    # The judge was kept BLIND to the trust tier (§15): the prompt names the source host but none of
    # our classified tier labels.
    prompt = judge.prompts[0].lower()
    assert "ling.example.edu" in prompt  # the source host is shown (the judge can weigh it)
    assert "trust" not in prompt
    for tier in ("official", "reputable", "blocked"):
        assert tier not in prompt


async def test_curate_forces_video_kind_for_a_youtube_search_result() -> None:
    # Arrange — a youtube link arrives under a non-video (article) query. The deterministic classifier
    # must override the query's kind so the reader plays it instead of rendering a READ/ARTICLE card.
    youtube = SearchResult(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Editing for register and tone",
        snippet="annotated examples of register and tone shifts",
    )
    judge = _FakeJudge(
        '{"selected": [{"index": 0, "phase": "demonstrate", "why": "w", "credibility": 0.8}]}'
    )
    curator = ClaudeResourceCurator(
        judge,
        StubSearchProvider([youtube]),
        StubVideoSource(),
        translator=_OneQueryTranslator(
            SearchQuery(kind=ResourceKind.ARTICLE, query="register and tone editing")
        ),
    )

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — the youtube result is reclassified VIDEO despite the article query.
    kept = curated.activate + curated.demonstrate + curated.apply + curated.integrate
    assert len(kept) == 1
    assert kept[0].kind is ResourceKind.VIDEO


async def test_curate_degrades_to_empty_without_calling_the_judge_when_no_candidates() -> None:
    # Arrange — empty search + empty video source (the no-key / nothing-found path).
    judge = _FakeJudge("{}")
    curator = ClaudeResourceCurator(judge, StubSearchProvider(), StubVideoSource())

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — no resources on any phase, and the judge was never invoked (no candidates to vet).
    assert curated.activate == []
    assert curated.demonstrate == []
    assert curated.apply == []
    assert curated.integrate == []
    assert judge.prompts == []


def test_build_curation_prompt_feeds_content_and_stays_blind_to_trust() -> None:
    # Arrange — a candidate carrying the search snippet + the query's good_result + level hint.
    views = [
        CandidateView(
            index=0,
            kind=ResourceKind.VIDEO,
            title="Some catchy title",
            source="youtube.com",
            url="https://youtu.be/x",
            snippet="A worked example halving the search range each comparison.",
            good_result_looks_like="worked example with a real trace",
            level_hint="advanced",
        )
    ]

    # Act
    prompt = build_curation_prompt(_module(), views, limit=4)

    # Assert — the judge sees CONTENT (snippet), the target signal, and the level — but no tier.
    assert "halving the search range" in prompt
    assert "worked example with a real trace" in prompt
    assert "advanced" in prompt
    assert "trust" not in prompt.lower()
    for tier in ("official", "reputable", "blocked"):
        assert tier not in prompt.lower()


async def test_curate_over_retrieves_and_feeds_the_query_content_signal_to_the_judge() -> None:
    # Arrange — a translator emitting one article query with a content signal; a recording search.
    search = _RecordingSearch(
        [
            SearchResult(
                url="https://b.example.edu/x", title="Title", snippet="dense authentic input"
            )
        ]
    )
    judge = _FakeJudge(
        '{"selected": [{"index": 0, "phase": "apply", "why": "w", "credibility": 0.6}]}'
    )
    curator = ClaudeResourceCurator(
        judge,
        search,
        StubVideoSource(),
        translator=_OneQueryTranslator(
            SearchQuery(
                kind=ResourceKind.ARTICLE,
                query="advanced listening input",
                good_result_looks_like="unscripted native-pace discussion",
                level_hint="C1",
            )
        ),
    )

    # Act
    await curator.curate(_module(), _brief())

    # Assert — search over-retrieved (a real pool, well above the old fixed cap of 4), and the judge
    # saw the content signals.
    assert search.max_results and search.max_results[0] >= 10
    prompt = judge.prompts[0]
    assert "dense authentic input" in prompt  # the search snippet reaches the judge
    assert "unscripted native-pace discussion" in prompt  # the query's good_result_looks_like
    assert "C1" in prompt  # the level hint


async def test_curate_drops_unplayable_videos_and_blends_the_metric_into_credibility() -> None:
    # Arrange — two videos: one non-embeddable (dropped by the guard), one enriched + embeddable.
    dead = VideoResult(url="https://youtu.be/dead", title="Dead", embeddable=False)
    good = VideoResult(
        url="https://youtu.be/good",
        title="Good",
        channel="Chan",
        duration="12:00",
        duration_seconds=720,
        has_captions=True,
        embeddable=True,
    )
    # The judge can only keep index 0 — i.e. the survivor after the guard drops the dead one.
    judge = _FakeJudge(
        '{"selected": [{"index": 0, "phase": "demonstrate", "why": "w", "credibility": 1.0}]}'
    )
    curator = ClaudeResourceCurator(
        judge,
        StubSearchProvider(),
        StubVideoSource([dead, good]),
        translator=_OneQueryTranslator(SearchQuery(kind=ResourceKind.VIDEO, query="q")),
        clock=lambda: "2026-06-03T00:00:00Z",
    )

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — only the playable video reached the judge + was kept (the dead one was guarded out).
    assert len(curated.demonstrate) == 1
    kept = curated.demonstrate[0]
    assert kept.url == "https://youtu.be/good"
    # The deterministic metric (healthy duration + captions → 0.75) blended into the judge's 1.0:
    # round(0.7*1.0 + 0.3*0.75, 2) = 0.92 — pinned so a scorer/blend regression can't slip through.
    assert kept.credibility == 0.92


async def test_curate_retries_with_a_broaden_feedback_when_the_first_pass_is_empty() -> None:
    # Arrange — the first search returns nothing; the translator records the feedback it's given.
    search = _EmptyOnFirstPassSearch(
        [SearchResult(url="https://b.example.edu/x", title="Found on the broader pass")]
    )
    translator = _FeedbackAwareTranslator(SearchQuery(kind=ResourceKind.ARTICLE, query="q"))
    judge = _FakeJudge(
        '{"selected": [{"index": 0, "phase": "apply", "why": "w", "credibility": 0.6}]}'
    )
    curator = ClaudeResourceCurator(judge, search, StubVideoSource(), translator=translator)

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — a second (broaden) pass ran, and it recovered a resource instead of a silent zero.
    assert translator.feedbacks == [
        None,
        "previous queries returned 0 results; broaden and use simpler, more common phrasing",
    ]
    total = len(curated.activate + curated.demonstrate + curated.apply + curated.integrate)
    assert total == 1


async def test_curate_respects_the_resource_budget() -> None:
    # Arrange — two candidates the judge keeps, but a budget of one resource.
    video = VideoResult(url="https://youtu.be/a", title="A")
    article = SearchResult(url="https://b.example.edu/x", title="B")
    judge = _FakeJudge(
        '{"selected": ['
        '{"index": 0, "phase": "demonstrate", "why": "a", "credibility": 0.9},'
        '{"index": 1, "phase": "apply", "why": "b", "credibility": 0.9}]}'
    )
    curator = ClaudeResourceCurator(
        judge,
        StubSearchProvider([article]),
        StubVideoSource([video]),
        budget=ResourceBudget(max_searches=4, max_resources=1),
    )

    # Act
    curated = await curator.curate(_module(), _brief())

    # Assert — only the first selection is kept (budget cap held, first-wins by selection order):
    # the demonstrate video survives, the apply article is dropped.
    total = len(curated.activate + curated.demonstrate + curated.apply + curated.integrate)
    assert total == 1
    assert len(curated.demonstrate) == 1
    assert curated.apply == []
