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
    build_resource_queries,
)
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
