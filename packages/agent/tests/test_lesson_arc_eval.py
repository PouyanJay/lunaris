"""P7.3 — the lesson-arc eval (live, key-gated).

The headline guarantee of the arc fix: a real author, given a researched brief + a module's
competency, writes a lesson as the ARC (entry expectations + a self-check around the teaching
phases) rather than a bare Merrill cycle. Deselected by default; run with a live Anthropic key via
``-m eval``. The offline ``test_authoring_prompt`` suite proves the prompt + wiring
deterministically; this proves the end-to-end outcome against the live model.
"""

import os

import pytest
from lunaris_agent.subagents.module_author import ClaudeModuleAuthor
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    DetailDepth,
    LanguageStyle,
    Level,
    Module,
    Objective,
    Preferences,
)

pytestmark = pytest.mark.eval

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"


async def test_advanced_lesson_is_authored_as_the_arc_with_expects_and_self_check() -> None:
    # Arrange — an advanced module mapped to a researched competency, with a personalized brief.
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the lesson-arc eval needs a live model")
    author = ClaudeModuleAuthor(os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER))
    module = Module(
        id="m-intent",
        title="Hearing implied intent and hedged disagreement",
        kcs=["intent"],
        competency="understand implied meaning and hedged disagreement in spoken English",
        objectives=[
            Objective(
                statement="Given an audio clip, the learner can analyze the speaker's intent.",
                bloom_level=BloomLevel.ANALYZE,
                kc="intent",
            )
        ],
        difficulty_index=0.8,
    )
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across listening, reading, writing, and speaking",
        target_level=Level.ADVANCED,
        assumed_prior="strong everyday English (around CLB 8-9)",
        preferences=Preferences(
            detail_depth=DetailDepth.IN_DEPTH, language_style=LanguageStyle.SOPHISTICATED
        ),
    )
    frontier = ["the English alphabet", "basic vocabulary", "everyday conversation"]

    # Act
    draft = await author.author(module, brief=brief, frontier=frontier)

    # Assert — the lesson came back as the ARC: it opens with entry expectations and closes with a
    # self-check (the bookends the bare Merrill cycle lacked), and the teaching phases have prose.
    assert draft.expects, "the arc has no 'expects' bookend (entry expectations)"
    assert draft.self_check, "the arc has no 'self_check' bookend (self-assessment)"
    assert draft.demonstrate.prose.strip(), "the demonstrate phase has no worked example / strategy"
    assert draft.apply.prose.strip(), "the apply phase has no practice"
