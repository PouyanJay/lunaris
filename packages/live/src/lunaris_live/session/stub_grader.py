import re

from ..graph.schema import ConceptNode, MasteryCriterion
from .schema import EvidenceKind, TurnGrade

#: Words that carry no signal about whether a bar was met. Tokens under four characters go the same
#: way, which takes out most of English's connective tissue for free.
_NOISE = frozenset(
    {
        "about",
        "because",
        "could",
        "does",
        "from",
        "should",
        "that",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "what",
        "when",
        "which",
        "with",
        "would",
        "your",
        "yours",
    }
)

_MIN_WORD = 4

#: Share of the criterion's content words the answer has to touch. Two thresholds, because the loop
#: needs all three verdicts to be reachable offline: a stub that could only pass or only fail would
#: leave either remediation or progression untested below the API.
_MET_OVERLAP = 0.5
_PARTIAL_OVERLAP = 0.25


class StubGrader:
    """A grader that needs no model, no key and no network.

    It is emphatically not pretending to judge understanding — it measures how much of the
    criterion's own vocabulary the answer touches. That is a crude proxy and a deliberate one: it is
    deterministic, it is directionally sane (a shrug fails, a restatement in kind passes), and it
    can reach all three verdicts, which is what lets the offline suite drive the loop *both* ways.
    Real judgement is ``ClaudeGrader``, behind the same protocol.
    """

    async def grade(
        self, answer: str, *, criterion: MasteryCriterion, node: ConceptNode, run_id: str
    ) -> TurnGrade:
        asked = _content_words(criterion.statement)
        said = _content_words(answer)
        touched = asked & said
        overlap = len(touched) / len(asked) if asked else 0.0

        if overlap >= _MET_OVERLAP:
            return TurnGrade(kind=EvidenceKind.MET, reason="That covers what you were asked to do.")
        if overlap >= _PARTIAL_OVERLAP:
            return TurnGrade(
                kind=EvidenceKind.PARTIAL, reason="Part of it is there; the rest is missing."
            )
        return TurnGrade(kind=EvidenceKind.NOT_MET, reason="That does not answer what was asked.")


def _content_words(text: str) -> set[str]:
    """The words in ``text`` worth comparing: lowercased, de-punctuated, short ones dropped."""
    return {
        word
        for word in re.split(r"[^a-z0-9]+", text.lower())
        if len(word) >= _MIN_WORD and word not in _NOISE
    }
