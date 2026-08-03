import re

from .schema import ConceptGraph, ConceptNode

#: Words that appear in almost any question and identify almost nothing on their own.
_NOISE = frozenset(
    [
        "a",
        "about",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "could",
        "do",
        "does",
        "explain",
        "for",
        "from",
        "get",
        "give",
        "go",
        "happen",
        "happens",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "like",
        "me",
        "mean",
        "means",
        "more",
        "most",
        "my",
        "no",
        "not",
        "of",
        "on",
        "one",
        "or",
        "please",
        "should",
        "show",
        "so",
        "some",
        "tell",
        "test",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "things",
        "this",
        "to",
        "told",
        "use",
        "used",
        "using",
        "want",
        "was",
        "way",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "work",
        "works",
        "would",
        "you",
        "your",
    ]
)

#: How much of a concept's name the request has to have said. One word of a two-word name is not
#: enough; the whole of it is.
_MIN_SCORE = 1.0

#: …and how much of the *request* that overlap has to account for, when only one word matched.
#: "Explain bias" is about bias; "my opinion has a bias in it" is not, and the difference is
#: entirely whether the concept was most of what the learner said.
_MIN_FOCUS = 0.5


def resolve_request(graph: ConceptGraph, request: str) -> ConceptNode | None:
    """The concept a learner's question is about, or ``None`` if the map does not cover it.

    Matched by wording rather than id, because a learner does not use the compiler's vocabulary —
    "cost function" and "step size" are the same questions as "loss function" and "learning rate".
    Each concept is matched against its name and its aliases; the definition is left out, being
    prose written to explain and sharing too many words with everything else.

    ``None`` is a real answer, not a failure: it is the signal that sends the director to C1's
    extension. A confident wrong match is far worse — the tutor goes on to answer a question the
    learner never asked — so a single shared word only counts when it was most of what they said.

    Lexical, not semantic: deterministic, no embedding call, returns inside the same turn. It will
    miss an inflection ("what are gradients" against "Gradient"), which is the known cost of that
    choice. Swapping in embeddings later changes this function's body and nothing that calls it.
    """
    request_words = _words(request)
    if not request_words:
        return None

    best: tuple[float, ConceptNode] | None = None
    for node in graph.nodes:
        score = max(_score(request_words, _words(phrase)) for phrase in (node.name, *node.aliases))
        # Strictly better, so the first node wins a tie and the result stays reproducible.
        if score >= _MIN_SCORE and (best is None or score > best[0]):
            best = (score, node)

    return best[1] if best else None


def _words(text: str) -> set[str]:
    """Every word in a phrase, lowercased and depunctuated.

    Stopwords are kept here and weighed in ``_score`` rather than stripped now: dropping them this
    early leaves a concept genuinely named "Work" with no words at all, unmatchable by any phrasing
    — and an on-map concept that always looks off-map would trigger extension after extension for
    something the map already has.
    """
    return {word for word in re.split(r"[^a-z0-9]+", text.lower()) if word}


def _score(request: set[str], concept: set[str]) -> float:
    """How much of the concept's name the request said, discounted if it said little else.

    Scored against the *concept*, not the request: a long question that names a concept in full has
    identified it, and dividing by the question's length would punish a learner for elaborating.
    Longer names therefore score higher when matched fully, so "gradient descent step" beats
    "gradient" on a request naming both.

    Overlapping only on common words counts for nothing — unless the concept's own name is made of
    them, in which case those words are all it has to be recognised by.
    """
    if not concept:
        return 0.0

    overlap = request & concept
    signal = overlap if concept <= _NOISE else overlap - _NOISE
    if not signal:
        return 0.0

    score = len(signal) * (len(signal) / len(concept))
    if len(signal) > 1:
        return score

    # One word matched. It only identifies the concept if it was the substance of the request —
    # otherwise every passing mention of "bias" or "state" resolves to a concept of that name.
    meaningful = request - _NOISE or request
    return score if len(signal) / len(meaningful) >= _MIN_FOCUS else 0.0
