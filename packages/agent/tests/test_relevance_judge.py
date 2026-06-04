"""P6.3 (T6) — the discovery relevance judge is BLIND to a source's trust label (§3 / §10).

Discovery's gate scores a source's trust (the Verifier's job) AND judges its topical relevance (the
judge's job) — the two must stay separate, or an authority badge could bias the on-topic verdict.
The Protocol enforces this structurally (``is_relevant`` takes only the concept + the text — never a
URL or tier), and the live judge's prompt reflects that: it carries the concept + the page text,
never the domain, tier, or credibility.
"""

from typing import Any

from lunaris_agent.harness.discovery import ClaudeRelevanceJudge, StubRelevanceJudge


class _CapturingModel:
    """A fake chat model that records the prompt it gets and returns a fixed relevant verdict."""

    def __init__(self) -> None:
        self.prompt: str | None = None

    async def ainvoke(self, prompt: str, **_kwargs: Any) -> "_Message":
        self.prompt = prompt
        return _Message('{"relevant": true, "reason": "on topic"}')


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


async def test_the_judge_prompt_carries_the_concept_and_text_but_not_the_trust_label() -> None:
    # Arrange — a high-trust source's text. The gate already knows its tier (it scored it), but the
    # judge must be handed only the concept + the text.
    model = _CapturingModel()
    judge = ClaudeRelevanceJudge(model)

    # Act
    verdict = await judge.is_relevant(
        kc_label="Dijkstra's algorithm",
        kc_definition="finds shortest paths in a weighted graph",
        text="This peer-reviewed article explains how Dijkstra's algorithm finds shortest paths.",
    )

    # Assert — the verdict parses, and the prompt is about topicality only: the concept + text are
    # present, but no trust tier / credibility / domain leaks in to bias the judgement.
    assert verdict.relevant is True
    prompt = model.prompt or ""
    assert "Dijkstra's algorithm" in prompt
    assert "finds shortest paths" in prompt
    lowered = prompt.lower()
    assert "reputable" not in lowered
    assert "official" not in lowered
    assert "credibility" not in lowered
    assert "trust tier" not in lowered
    assert "example.com" not in lowered


async def test_an_unparseable_judge_response_keeps_the_source_for_the_verifier() -> None:
    # Arrange — the model returns prose, not JSON (a degraded response).
    class _Prose:
        async def ainvoke(self, prompt: str, **_kwargs: Any) -> _Message:
            return _Message("I think this looks fine, honestly.")

    judge = ClaudeRelevanceJudge(_Prose())

    # Act
    verdict = await judge.is_relevant(kc_label="x", kc_definition="y", text="z")

    # Assert — best-effort: an unreadable verdict keeps the source (the trust floor is the real
    # gate), never a silent drop of possibly-good evidence.
    assert verdict.relevant is True


async def test_the_stub_judge_is_blind_by_construction() -> None:
    # The Protocol the gate calls has no URL/tier parameter, so the stub (and any impl) cannot see a
    # trust label even if it wanted to — relevance is decided on the concept + text alone.
    verdict = await StubRelevanceJudge().is_relevant(
        kc_label="binary search", kc_definition="halving search", text="A guide to binary search."
    )
    assert verdict.relevant is True
