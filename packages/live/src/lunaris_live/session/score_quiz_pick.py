from ..graph.schema import ConceptNode
from .max_answer_chars import MAX_ANSWER_CHARS
from .schema import EvidenceKind, QuizCard, SurfaceSpec, TurnGrade

#: ``TurnGrade.reason`` is bounded at 500, and a quoted option is not: a definition may run to 2000
#: characters and a misconception is unbounded. Quoted first and clipped to what is left, so the
#: learner always sees which statement they picked even when it had to be shortened.
_REASON_CHARS = 500

_RECOGNISED = (
    "That is the true one. Picking it out of the lineup shows you recognise it. The bar asks you "
    "to put it in your own words, so this takes you part of the way there."
)

_MISTAKEN = (
    'You picked "{option}". That is one of the wrong models this concept attracts, '
    "not the true one."
)


def score_quiz_pick(
    said: str, *, surface: SurfaceSpec | None, node: ConceptNode
) -> TurnGrade | None:
    """The verdict on a picked option, or ``None`` when this answer was not a pick.

    Recognition is marked here, deterministically, and never by the prose grader. A quiz's true
    option is the concept's ``definition`` verbatim while the criterion a turn stages asks the
    learner to *explain* the mechanism in their own words, so handing a pick to the grader marks a
    definition against a demand for production and refuses the correct answer, which is what
    happened to the first learner who met one of these cards. Plan §8 makes deterministic behaviour
    mandatory for this tier precisely because it feeds the learner model.

    **The browser still never learns the answer key.** ``QuizCard`` deliberately omits which option
    is true, and that stays exactly as it is: the truth is known here, on the server, where the
    learner cannot read it and where there is only ever one assessment path.

    ``None`` (meaning "not a pick, judge it as prose") for anything that is not a standing quiz
    card, and for text that matches no option on the card in front of the learner. The composer
    stays open while a card stands (P2b T10), so a learner may write instead of picking, and prose
    that happens to quote the definition back is a claim the grader still has to judge. Which is
    why the truth is looked for *among the options* rather than beside them: a definition the
    learner was never shown cannot have been picked, so matching it is writing, not recognising.

    The comparison is made on ``take_turn``'s footing at both ends: it strips and truncates the
    answer before anything sees it, so an option long enough to be truncated would otherwise fail to
    match itself.
    """
    if not isinstance(surface, QuizCard) or surface.node_id != node.id:
        # The card and the turn's move name their concepts separately. Today ``select_surface``
        # builds both from one node, so they cannot disagree, and if they ever did, marking a pick
        # against another concept's definition is exactly the silent corruption plan §8 warns
        # about. Falling through to the grader is the safe end of that branch.
        return None

    picked = _as_answered(said)
    truth = _as_answered(node.definition)
    for option in surface.options:
        if picked != _as_answered(option):
            continue
        if picked == truth:
            return TurnGrade(kind=EvidenceKind.PARTIAL, reason=_RECOGNISED)
        # Named rather than merely refused: misconceptions are first-class entries in the learner
        # model (plan §10) and the director's remediation keys off *which* wrong model somebody
        # holds. This is the one moment it is knowable exactly rather than inferred.
        return TurnGrade(kind=EvidenceKind.NOT_MET, reason=_mistaken_reason(option))

    return None


def _as_answered(text: str) -> str:
    """``text`` as ``take_turn`` would have it after a learner sent it."""
    return text.strip()[:MAX_ANSWER_CHARS]


def _mistaken_reason(option: str) -> str:
    """The refusal, with the picked statement quoted and clipped to fit the field."""
    room = _REASON_CHARS - len(_MISTAKEN.format(option=""))
    quoted = option if len(option) <= room else f"{option[: max(1, room - 1)]}…"
    return _MISTAKEN.format(option=quoted)
