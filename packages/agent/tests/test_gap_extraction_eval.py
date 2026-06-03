"""P7.1 — the anti-alphabet regression eval (live, key-gated).

The headline guarantee of the relevance fix: an ADVANCED goal must not be taught from the
foundations. Deselected by default; run with a real Anthropic key via ``-m eval``. This is the
end-to-end proof that gap-scoped extraction flips "CLB 10 → alphabet" into an advanced course — the
offline ``test_gap_extraction`` proves the instruction + wiring deterministically.
"""

import os

import pytest
from lunaris_agent.subagents.concept_extractor import ClaudeConceptExtractor
from lunaris_runtime.schema import CourseBrief, Level

pytestmark = pytest.mark.eval

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
# Foundations a CLB 10 (advanced) course must never teach — the deny-set. Terms are specific enough
# to avoid false positives on advanced KCs (e.g. "letter of the alphabet", not bare "letters").
_FOUNDATION_TERMS = [
    "alphabet",
    "phonetic",
    "letter of the alphabet",
    "basic vocabulary",
    "spelling basics",
]


async def test_advanced_english_brief_extracts_the_gap_not_the_foundations() -> None:
    # Arrange — the motivating failure case: advanced English toward CLB 10.
    extractor = ClaudeConceptExtractor(os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER))
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across listening, reading, writing, and speaking",
        target_level=Level.ADVANCED,
        assumed_prior="strong everyday English (around CLB 8-9)",
    )
    frontier = ["the English alphabet", "basic vocabulary", "core grammar", "everyday conversation"]

    # Act
    extraction = await extractor.extract(
        "Improve my English to achieve CLB 10", brief=brief, frontier=frontier
    )

    # Assert — non-vacuous, and no extracted KC is a foundation (the alphabet-up bug is dead).
    assert extraction.kcs, "the extractor returned no knowledge components"
    haystack = " ".join(f"{kc.label} {kc.definition}".lower() for kc in extraction.kcs)
    leaked = [term for term in _FOUNDATION_TERMS if term in haystack]
    assert not leaked, f"advanced course wrongly extracted foundations: {leaked}"
