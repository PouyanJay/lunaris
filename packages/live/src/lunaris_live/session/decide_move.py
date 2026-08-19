from ..graph import ConceptGraph, ConceptNode
from .claim_of import claim_of
from .is_demonstrated import is_demonstrated
from .mastery_thresholds import DECAYED as _DECAYED
from .mastery_thresholds import MASTERED as _MASTERED
from .recall_of import recall_of
from .schema import DirectorMove, LearnerModel, MoveKind, SessionClock

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
    4. **A claim is checked before anything is built on it** (P2c T3, U2). The placement interview
       lets a learner skip a chain they say they know, to its boundary; the deepest claim the next
       concept stands on is retrieved and graded first. Held rather than trusted, because the
       number that skips a curriculum must only ever be written by the grader.
    5. **Otherwise, teach something new whose prerequisites are met** — or credibly claimed.
    6. **Nothing left worth doing is a reason to stop**, not to loop.
    """
    if clock.is_spent:
        return DirectorMove(
            kind=MoveKind.CLOSE,
            reason=(
                f"The session's {round(clock.budget_s / 60)} minutes are up — better to end on a "
                "recap than mid-explanation."
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

    if (claimed := _boundary_claim(graph, model)) is not None:
        return DirectorMove(
            kind=MoveKind.RETRIEVE,
            node_id=claimed.id,
            reason=(
                f"{claimed.name} was named in the interview as already known, and what comes next "
                "stands on it — a quick check before building on it, so nothing is skipped on a "
                "guess."
            ),
        )

    if (next_up := _frontier(graph, model)) is not None:
        return DirectorMove(
            kind=MoveKind.INTRODUCE,
            node_id=next_up.id,
            # Two readings of one rule, because the trace is read by a human deciding whether the
            # policy is any good. A second pass over a concept the learner has already met is not
            # "the next thing this map can teach", and a reason that said so would be the one part
            # of the record that cannot be checked quietly telling them something untrue.
            reason=(
                f"{next_up.name} has been started but not yet shown, so the session stays with it "
                "rather than moving on."
                if _started(model, next_up.id)
                else f"Everything {next_up.name} depends on has been demonstrated or checked, so "
                "it is the next thing this map can teach."
            ),
        )

    return DirectorMove(
        kind=MoveKind.CLOSE,
        reason=(
            "Nothing on this map is left to introduce and nothing is due for review. Closing while "
            "the session still has a shape rather than padding it out."
        ),
    )


def _demonstrated(model: LearnerModel, node_id: str) -> bool:
    """Whether the learner has ever shown this concept — the belief at its last evidence, undecayed.

    Deliberately NOT the decayed recall, and running a whole session is what settled it. Recall
    dips below ``_MASTERED`` long before it falls under ``_DECAYED``, so a concept sitting in that
    band was neither "known" (the frontier offered it again) nor faded enough to retrieve — and the
    director taught it from scratch to somebody who had just proved it. Judging *what was earned*
    on the undecayed belief and *what has faded* on the decayed one keeps both rules honest, and it
    makes an unlock permanent: progress through the map is earned once, not re-earned every turn.

    One threshold and no separate evidence-count guard, because the threshold already implies one.
    A single piece of evidence moves the belief by ``_PULL`` (0.45), which is below ``_MASTERED``
    (0.6) by construction — so mastery necessarily takes more than one answer, and a guard saying so
    again would be a second place to keep the same rule true. That relationship is what
    ``test_one_right_answer_does_not_unlock_the_next_concept`` pins.
    """
    return is_demonstrated(model.nodes.get(node_id))


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
        if is_demonstrated(model.nodes.get(node.id))
    ]
    due = [(recall, node) for recall, node in candidates if recall < _DECAYED]
    return min(due, key=lambda pair: pair[0])[1] if due else None


def _claimed(model: LearnerModel, node_id: str) -> bool:
    """A concept the placement interview says the learner holds, and nothing has checked yet.

    A claim credits a concept for the frontier's purposes only — the learner is not walked through
    a chain they say they know — and it lasts exactly until the first evidence, which either makes
    it real (``apply_evidence`` from the claim) or drops it. A hesitant claim (under the mastery
    bar) credits nothing: it is a band for Tier 2, not a reason to skip.

    Deliberately not re-validated against the concept's own ``requires`` the way ``_frontier``
    re-validates an introduction: a claim promotes to a RETRIEVE, which grades before it credits
    anything, whereas an INTRODUCE trusts the map's structure. A claim beneath a hole is caught by
    the frontier walk (pinned: a claim on a concept whose prerequisite is unclaimed skips nothing).
    """
    claim = claim_of(model.nodes.get(node_id))
    return claim is not None and claim >= _MASTERED


def _credited(model: LearnerModel, node_id: str) -> bool:
    """Demonstrated, or credibly claimed: what the frontier walks over."""
    return _demonstrated(model, node_id) or _claimed(model, node_id)


def _boundary_claim(graph: ConceptGraph, model: LearnerModel) -> ConceptNode | None:
    """The claim to check before the frontier is taught: the deepest *unvouched* claim the next
    concept stands on — or, when nothing is left to introduce, the deepest unvouched claim on the
    map.

    A claim is vouched for once the learner has demonstrated a concept that stands on it: a MET on
    the top of a claimed chain is evidence for the chain, so the claims beneath it are not checked
    one by one (found by driving the real loop: the director verified downward after the top held).
    "Deepest" is the last in teaching order — the one the frontier directly stands on. Checking it
    is enough to cross the boundary: if it holds, the chain beneath held well enough to get there;
    if it does not, the frontier moves back to it and *its* deepest unvouched claim is checked next,
    so a verification walks back down the chain until something holds. Everything claimed and
    nothing checked is not a finished map: it is a boundary at the last claim.
    """
    frontier = _frontier(graph, model)
    candidates = _unvouched_claims(
        graph, model, frontier.requires if frontier is not None else list(graph.topo_order)
    )
    if not candidates:
        return None
    order = {node_id: index for index, node_id in enumerate(graph.topo_order)}
    return max(candidates, key=lambda node: order.get(node.id, -1))


def _unvouched_claims(
    graph: ConceptGraph, model: LearnerModel, node_ids: list[str]
) -> list[ConceptNode]:
    """Of ``node_ids``, the concepts on the map that are claimed and that no demonstrated concept
    stands on."""
    by_id = {node.id: node for node in graph.nodes}
    vouched = _vouched(graph, model)
    return [
        by_id[node_id]
        for node_id in node_ids
        if node_id in by_id and _claimed(model, node_id) and node_id not in vouched
    ]


def _started(model: LearnerModel, node_id: str) -> bool:
    """Whether the learner has been taught this concept at all: real evidence, not a row. A claim
    seeds a row with none (P2c T3), and a reason that called a claimed-and-never-taught concept
    "started" would be the trace telling somebody something untrue (found in review)."""
    known = model.nodes.get(node_id)
    return known is not None and known.evidence_count > 0


def _vouched(graph: ConceptGraph, model: LearnerModel) -> set[str]:
    """Every concept some demonstrated concept stands on, transitively: claims there are vouched
    for by the evidence above them and are not checked on their own."""
    by_id = {node.id: node for node in graph.nodes}
    vouched: set[str] = set()
    pending = [
        required
        for node in graph.nodes
        if _demonstrated(model, node.id)
        for required in node.requires
    ]
    while pending:
        node_id = pending.pop()
        if node_id in vouched or node_id not in by_id:
            continue
        vouched.add(node_id)
        pending.extend(by_id[node_id].requires)
    return vouched


def _frontier(graph: ConceptGraph, model: LearnerModel) -> ConceptNode | None:
    """The next concept worth teaching: not yet credited, everything it needs already credited.

    "Credited" is demonstrated on the undecayed belief, or credibly claimed in placement (P2c T3),
    so a concept the learner has demonstrated is never introduced a second time — whatever else the
    session does with it, teaching it again from scratch is the one move that tells somebody their
    work did not count — and a chain they say they know is walked over rather than through. What
    is claimed and not checked is checked before it is built on (``_boundary_claim``).

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
        if node is None or _credited(model, node_id):
            continue
        if all(_credited(model, required) for required in node.requires):
            return node
    return None
