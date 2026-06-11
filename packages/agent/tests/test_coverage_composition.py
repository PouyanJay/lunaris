"""CQ Phase 4.2 — the composition root key-gates the coverage critic on ``ANTHROPIC_API_KEY``.

With an Anthropic key the agent pipeline wires the live LLM coverage judge; without one it wires the
deterministic structural fail-safe directly — so the gate always runs and the no-key CI path stays
deterministic.
"""

import pytest
from lunaris_agent.composition._subagents import _coverage_critic_from_env
from lunaris_agent.coverage_critic import ClaudeCoverageCritic, DeterministicCoverageCritic

_STRONG = "claude-opus-4-8"


def test_coverage_critic_is_deterministic_without_an_anthropic_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — no Anthropic key configured.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Act / Assert — the structural fail-safe runs the gate with no model, keeping the path offline.
    assert isinstance(_coverage_critic_from_env(_STRONG), DeterministicCoverageCritic)


def test_coverage_critic_is_the_llm_judge_when_the_anthropic_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — an Anthropic key is present (constructing the critic touches no network).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    # Act / Assert — the live LLM judge is wired (not the fail-safe), so a regression substituting
    # the deterministic critic here would be caught.
    assert isinstance(_coverage_critic_from_env(_STRONG), ClaudeCoverageCritic)
