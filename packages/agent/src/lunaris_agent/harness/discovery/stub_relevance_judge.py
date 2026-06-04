import re

from .relevance_judge import RelevanceVerdict

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Tokens too generic to signal that a page actually teaches a concept (they match almost any text).
_STOPWORDS = frozenset({"the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with"})


class StubRelevanceJudge:
    """A deterministic, no-key relevance judge: a concept's label tokens must appear in the text.

    Lets the discovery loop run + be tested offline without a model: a source is relevant when any
    non-trivial token of the concept's label occurs in the extracted text (case-folded). Blind to
    trust labels by construction — it is only ever handed the concept and the text.
    """

    async def is_relevant(
        self, *, kc_label: str, kc_definition: str, text: str
    ) -> RelevanceVerdict:
        label_tokens = {
            token for token in _TOKEN_RE.findall(kc_label.lower()) if token not in _STOPWORDS
        }
        if not label_tokens:
            # Nothing distinctive to match on — be permissive (the contract: never drop on inability
            # to judge), leaving the verifier's trust floor as the real gate.
            return RelevanceVerdict(True, "no distinctive terms to check")
        text_tokens = set(_TOKEN_RE.findall(text.lower()))
        overlap = label_tokens & text_tokens
        if overlap:
            return RelevanceVerdict(True, f"Mentions {', '.join(sorted(overlap))}.")
        return RelevanceVerdict(False, f"No mention of “{kc_label}”.")
