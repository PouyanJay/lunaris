from .schema import LearnerModel

#: Turns without evidence for a belief to lose half the distance to its floor.
#:
#: Measured in TURNS, not wall time, so a session is reproducible: replaying the same answers yields
#: the same beliefs, which is what makes the simulated-learner eval (T9) mean anything. Real
#: cross-session forgetting happens over days and is NOT modelled here — recorded as an open
#: question rather than guessed at, because a curve invented now would be indistinguishable from a
#: fitted one to everything downstream, which is the dangerous kind of placeholder.
_HALF_LIFE_TURNS = 12.0

#: The share of a belief that decay can never take. A concept demonstrated once is not the same as
#: one never seen — the director should prefer *retrieving* the first over introducing it from
#: scratch — so recall approaches this floor rather than zero.
_FLOOR = 0.25


def recall_of(model: LearnerModel, node_id: str, *, at_turn: int) -> float:
    """What the learner is believed to recall about ``node_id`` **now**, at ``at_turn``.

    The stored estimate is the belief at its last evidence; this is that belief seen through the
    turns since. Without decay, spaced retrieval would have nothing to be spaced against — every
    concept would sit at whatever its last answer left it at forever, and the director would never
    look back at anything.

    A concept with no evidence answers ``0.0``: assuming knowledge would have the director skip
    concepts the learner has never seen, and ignorance is the safe direction to be wrong in.
    """
    known = model.nodes.get(node_id)
    if known is None:
        return 0.0

    elapsed = max(0, at_turn - known.last_evidence_turn)
    # Half the *distance to the floor* per half-life, so a stronger belief is still ahead of a
    # weaker one after the same wait — which is the whole point of repetition.
    retained = 0.5 ** (elapsed / _HALF_LIFE_TURNS)
    floor = known.estimate * _FLOOR
    return floor + (known.estimate - floor) * retained
