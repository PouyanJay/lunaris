from ..graph import ConceptGraph, ConceptNode
from .recall_of import recall_of
from .schema import DirectorMove, EvidenceKind, LearnerModel, MoveKind, SessionClock

#: Recall at or above this counts as "the learner has this". It gates introductions, so it is the
#: number that decides whether progress through the map is earned or waved through. Set above what a
#: single MET can reach (one piece of evidence lands at 0.45), so mastery takes more than one right
#: answer — a guess must not unlock a dependent.
_MASTERED = 0.6

#: Recall below this on a concept the learner HAS demonstrated means it is slipping and is worth
#: coming back to. Under ``_MASTERED`` by design: a concept between the two is neither solid enough
#: to build on nor faded enough to interrupt for.
_DECAYED = 0.45

#: Consecutive misses before the director stops advancing and changes approach. Two, not one: a
#: learner is allowed to be wrong once — that is what a first attempt is for — but a second miss on
#: the same concept means the explanation is not landing, and saying it louder will not help.
_STUCK_AFTER = 2


def decide_move(graph: ConceptGraph, model: LearnerModel, clock: SessionClock) -> DirectorMove:
    """What the session should do next, and why.

    A scored rule set rather than a model call (plan §7): legible, deterministic, exhaustively
    testable without a key, and the place pedagogical iteration will happen once there is real
    session data to iterate against. Rules are tried in a fixed order, and the order IS the policy:

    1. **The clock outranks everything.** A session is bounded by design, and the strongest teaching
       instinct must still not run it past its budget.
    2. **A stuck learner is not walked away from.** There is nearly always other material available;
       leaving somebody stranded on the concept they just failed twice to reach for something easier
       is the single worst thing this policy could do.
    3. **A slipping concept interrupts new material.** Spaced retrieval only exists if it can
       interrupt — a director that introduced whenever anything was introducible would never come
       back to anything.
    4. **Otherwise, teach something new whose prerequisites are met.**
    5. **Nothing left worth doing is a reason to stop**, not to loop.
    """
    if clock.is_spent:
        return DirectorMove(
            kind=MoveKind.CLOSE,
            reason=(
                f"The session's {round(clock.budget_s / 60)} minutes are up. Stopping here so it "
                "ends on a recap rather than mid-explanation."
            ),
        )

    if (stuck := _stuck_on(graph, model)) is not None:
        return DirectorMove(
            kind=MoveKind.REMEDIATE,
            node_id=stuck.id,
            reason=(
                f"{stuck.name} has been missed {_STUCK_AFTER} times running, so the explanation is "
                "not landing. Trying it a different way rather than pressing on."
            ),
        )

    if (slipping := _most_decayed(graph, model, clock)) is not None:
        return DirectorMove(
            kind=MoveKind.RETRIEVE,
            node_id=slipping.id,
            reason=(
                f"{slipping.name} was understood earlier but has not been used since. Coming back "
                "to it now, while recovering it is still cheap."
            ),
        )

    if (next_up := _frontier(graph, model, clock)) is not None:
        return DirectorMove(
            kind=MoveKind.INTRODUCE,
            node_id=next_up.id,
            reason=(
                f"Everything {next_up.name} depends on has been demonstrated, so it is the next "
                "thing this map can teach."
            ),
        )

    return DirectorMove(
        kind=MoveKind.CLOSE,
        reason=(
            "Nothing on this map is left to introduce and nothing is due for review. Closing while "
            "the session still has a shape rather than padding it out."
        ),
    )


def _knows(model: LearnerModel, node_id: str, clock: SessionClock) -> bool:
    """Whether the learner may be built on for ``node_id``: believed, now, at this turn.

    One threshold and no separate evidence-count guard, because the threshold already implies one.
    A single piece of evidence moves the belief by ``_PULL`` (0.45), which is below ``_MASTERED``
    (0.6) by construction — so mastery necessarily takes more than one answer, and a guard saying so
    again would be a second place to keep the same rule true. That relationship is what
    ``test_one_right_answer_does_not_unlock_the_next_concept`` pins: raise the pull past the
    threshold and it fails, which is the honest way to hold this invariant.
    """
    known = model.nodes.get(node_id)
    return known is not None and recall_of(model, node_id, at_turn=clock.turn) >= _MASTERED


def _stuck_on(graph: ConceptGraph, model: LearnerModel) -> ConceptNode | None:
    """The concept the learner is stuck on, if any.

    Read off the *belief* rather than a miss counter, so a breakthrough clears it: a concept that
    was hard once must not be remediated forever, or the session never moves. A learner is stuck
    when they have real evidence about a concept and that evidence has left the belief where a
    string of misses would — nowhere near mastery.
    """
    for node in graph.nodes:
        known = model.nodes.get(node.id)
        if known is not None and known.evidence_count >= _STUCK_AFTER and known.estimate < _DECAYED:
            return node
    return None


def _most_decayed(
    graph: ConceptGraph, model: LearnerModel, clock: SessionClock
) -> ConceptNode | None:
    """The demonstrated concept that has slipped furthest, if one has slipped at all.

    Only concepts the learner has actually demonstrated are candidates: recall of an unseen concept
    is 0.0, which is below any threshold, so a naive rule here would "retrieve" something that was
    never taught.
    """
    candidates = [
        (recall_of(model, node.id, at_turn=clock.turn), node)
        for node in graph.nodes
        if (known := model.nodes.get(node.id)) is not None and known.estimate >= _MASTERED
    ]
    due = [(recall, node) for recall, node in candidates if recall < _DECAYED]
    return min(due, key=lambda pair: pair[0])[1] if due else None


def _frontier(graph: ConceptGraph, model: LearnerModel, clock: SessionClock) -> ConceptNode | None:
    """The next concept worth teaching: not yet known, everything it needs already demonstrated.

    Walked in the map's own teaching order so two sessions on one map agree about what comes next,
    and so the choice inherits Phase 1's ordering rather than inventing a second one.

    The prerequisite check looks redundant against a *valid* ``topo_order`` — the first unknown
    concept in teaching order has all its prerequisites behind it, and they were only skipped
    because they were known. It is kept because the director does not own the order it is handed.
    C1 grows a map at runtime, ``prerequisites_of`` and ``resolve_request`` are public functions
    anyone can call with a hand-built graph, and a stale or invented ``topo_order`` would otherwise
    have this teach a concept on top of nothing. Pinned by
    ``test_a_lying_teaching_order_cannot_smuggle_a_concept_past_its_prerequisites``.
    """
    by_id = {node.id: node for node in graph.nodes}
    for node_id in graph.topo_order:
        node = by_id.get(node_id)
        if node is None or _knows(model, node_id, clock):
            continue
        if all(_knows(model, required, clock) for required in node.requires):
            return node
    return None


#: Re-exported for the grader (T5), which needs the same notion of "met" the director gates on —
#: two definitions of mastery would let a session award progress the policy refuses to act on.
MASTERY_EVIDENCE = EvidenceKind.MET
