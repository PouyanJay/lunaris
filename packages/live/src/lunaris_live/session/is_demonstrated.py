from .mastery_thresholds import MASTERED
from .schema import NodeKnowledge


def is_demonstrated(known: NodeKnowledge | None) -> bool:
    """Whether the learner has shown this concept: the belief at its last evidence over the mastery
    bar. One predicate for the director, the meter and the recap, so "what counts as mastered" lives
    in one place (it lived in three by P2c T5).

    One threshold and no separate evidence-count guard, because the threshold implies one: a single
    piece of evidence moves the belief by ``_PULL`` (0.45), under ``MASTERED`` (0.6), and a claim
    keeps ``estimate`` at nothing (``seed_priors``), so no row is over the bar without evidence.
    Undecayed on purpose — see ``decide_move._demonstrated`` for why the earned bar is read on the
    belief at its last evidence and the faded one on the decayed recall.
    """
    return known is not None and known.estimate >= MASTERED
