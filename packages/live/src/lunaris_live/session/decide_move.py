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

#: How many pieces of evidence a concept gets before the session stops trying to land it today.
#:
#: The bar has already come down by then: two misses switch the ask from production to recognition
#: (``select_surface`` rule 4), which is a real and weaker instrument, and a correct pick banks
#: PARTIAL rather than nothing. What this bounds is the *pressing on*. Without an upper end a
#: concept below the mastery band is remediated on every turn for the rest of the session, and the
#: first real browser session spent six turns on concept one of about twenty (U4).
#:
#: Five rather than three: a learner who takes four goes and gets there has done the thing this
#: whole loop exists for, and cutting them off at three would be the system giving up before they
#: did. Provisional, like ``_PULL`` — the keyed eval is what should move it.
_GIVE_UP_AFTER = 5


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
    3. **A review that has come due is taken before new material** (P2c T6). The close put a
       date on every concept the session graded — held or still forming; a session opened on or
       after that date checks it first, longest overdue first. This is the only cross-session
       pull there is: beliefs do not decay between sittings, the ladder is what brings a concept
       back.
    4. **A slipping concept interrupts new material.** Spaced retrieval only exists if it can
       interrupt — a director that introduced whenever anything was introducible would never come
       back to anything.
    5. **A claim is checked before anything is built on it** (P2c T3, U2). The placement interview
       lets a learner skip a chain they say they know, to its boundary; the deepest claim the next
       concept stands on is retrieved and graded first. Held rather than trusted, because the
       number that skips a curriculum must only ever be written by the grader.
    6. **Otherwise, teach something new whose prerequisites are met** — or credibly claimed.
    7. **Nothing left worth doing is a reason to stop**, not to loop.
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
            # Worded off the rule that actually fired. The rule is belief-based, not a miss
            # counter (see ``_stuck_on``), so "missed 2 times running" was untrue of a learner who
            # got it once and then lost it — which is exactly the sequence the first real session
            # produced, and the trace said something that had not happened.
            reason=(
                f"{stuck.name} is not holding: enough has been asked about it to tell, and it is "
                "still not there. Trying it a different way rather than pressing on."
            ),
        )

    if (due := _longest_overdue(graph, model, clock)) is not None:
        return DirectorMove(
            kind=MoveKind.RETRIEVE,
            node_id=due.id,
            # Two readings, because the trace is read by a human: a concept on the ladder was held
            # at a close; one at the bottom (rung zero) was still forming when the day was set.
            reason=(
                f"{due.name} is due for review: it was held when a session last closed and the "
                "day set for checking it has come round. A quick retrieval before anything new."
                if model.nodes[due.id].review_stage > 0
                else f"{due.name} is due for review: it was still forming when a session last "
                "closed, and today is the day set for coming back to it. Checking where it stands "
                "before anything new."
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

    if parked := [node for node in graph.nodes if _parked(model, node.id)]:
        # Distinct from the close below, and not a nicety: "nothing is left to introduce" would be
        # untrue here. Something *is* left, and the session chose to stop pressing on it (U4). A
        # trace that reported the two the same way would hide the one decision a reader would most
        # want to question.
        return DirectorMove(
            kind=MoveKind.CLOSE,
            reason=(
                f"{parked[0].name} has not landed today and everything else here stands on it, so "
                "it is better left for another day than pressed on. It will come round again."
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

    Bounded above by ``_GIVE_UP_AFTER`` (U4). Past it the concept is not "unstuck", it is *left for
    another day*: the session moves on to something teachable, the belief is untouched (so nothing
    is credited that was not demonstrated, and dependents stay shut), and the close puts it on the
    review ladder like any other concept with evidence. A learner who cannot clear one bar must
    still be able to reach the other nineteen concepts on the map.
    """
    for node in graph.nodes:
        known = model.nodes.get(node.id)
        if known is None or known.estimate >= _DECAYED:
            continue
        if _STUCK_AFTER <= known.evidence_count < _GIVE_UP_AFTER:
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


def _longest_overdue(
    graph: ConceptGraph, model: LearnerModel, clock: SessionClock
) -> ConceptNode | None:
    """The concept whose scheduled review is furthest past ``clock.at``, if any is due at all.

    Read against the turn's wall time and nothing else: with no wall time (a replay, the prefetch
    prediction) nothing is due, because a ladder measured in days has no day to be read on. Ties
    fall to the map's teaching order, so two sittings on one map ask in the same order.
    """
    if clock.at is None:
        return None
    order = {node_id: index for index, node_id in enumerate(graph.topo_order)}
    due = [
        (known.due_at, order.get(node.id, len(order)), node)
        for node in graph.nodes
        if (known := model.nodes.get(node.id)) is not None
        and known.due_at is not None
        and known.due_at <= clock.at
    ]
    return min(due, key=lambda entry: entry[:2])[2] if due else None


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


def _credited(graph: ConceptGraph, model: LearnerModel) -> set[str]:
    """What the frontier walks over: every concept demonstrated or credibly claimed, and every
    concept one of those stands on, transitively (P2c T9).

    The downward part is the one the keyed eval found missing: a fluent learner's interview put
    claims on the gradient, the chain rule and backpropagation and none on the map's root — "slope
    and derivative", which nobody had asked them about — and the director introduced the root. If
    you know the gradient you know what a slope is: a credible claim credits what it stands on, and
    the check before the frontier is the claim that implies it (``_boundary_claim``). And a
    demonstration credits downward the same way, or the credit would vanish the moment the claim
    was checked and HELD (a MET clears the claim, T3) and the learner who had just explained the
    deepest concept in the chain would be walked back to its root — the identical move to the
    check having failed (found in review). It is AD12's own rule: a MET on the top of a chain is
    evidence for the chain. A hesitant claim credits nothing, itself included (T3). A prerequisite
    C1 grows beneath an already-demonstrated concept is therefore not taught either; that is the
    trade this makes, recorded rather than hidden.
    """
    by_id = {node.id: node for node in graph.nodes}
    credited: set[str] = set()
    pending = [
        node.id for node in graph.nodes if _demonstrated(model, node.id) or _claimed(model, node.id)
    ]
    while pending:
        node_id = pending.pop()
        if node_id in credited or node_id not in by_id:
            continue
        credited.add(node_id)
        pending.extend(by_id[node_id].requires)
    return credited


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
    if frontier is None:
        candidates = _unvouched_claims(graph, model, list(graph.topo_order))
    else:
        # What the frontier stands on: a claim there is the candidate; a prerequisite credited only
        # by implication (T9) is answered for by the claim that implies it, so that claim is.
        standing_on = [
            claim
            for required in frontier.requires
            for claim in (
                [required] if _claimed(model, required) else _claims_over(graph, model, required)
            )
        ]
        candidates = _unvouched_claims(graph, model, standing_on)
    if not candidates:
        return None
    order = {node_id: index for index, node_id in enumerate(graph.topo_order)}
    return max(candidates, key=lambda node: order.get(node.id, -1))


def _claims_over(graph: ConceptGraph, model: LearnerModel, node_id: str) -> list[str]:
    """The credibly claimed concepts that stand on ``node_id``, directly or through others: the
    claims whose credit reaches it by implication."""
    by_id = {node.id: node for node in graph.nodes}
    over: list[str] = []
    for node in graph.nodes:
        if not _claimed(model, node.id):
            continue
        beneath, pending = set(), list(node.requires)
        while pending:
            required = pending.pop()
            if required in beneath or required not in by_id:
                continue
            beneath.add(required)
            pending.extend(by_id[required].requires)
        if node_id in beneath:
            over.append(node.id)
    return over


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

    "Credited" is demonstrated on the undecayed belief, credibly claimed in placement (P2c T3), or
    beneath a credible claim (T9), so a concept the learner has demonstrated is never introduced a
    second time — whatever else the
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
    credited = _credited(graph, model)
    for node_id in graph.topo_order:
        node = by_id.get(node_id)
        if node is None or node_id in credited or _parked(model, node_id):
            continue
        if all(required in credited for required in node.requires):
            return node
    return None


def _parked(model: LearnerModel, node_id: str) -> bool:
    """Whether this concept has been left for another day (U4, T8).

    A concept the session has stopped pressing on is not a candidate to introduce again, or the
    give-up rule would only change which *kind* of move keeps landing on it: remediation stops and
    "started but not yet shown" takes over on the very next turn, which is the same loop wearing a
    different label. Found exactly that way.

    Not credited, though. Being moved on from and having shown it are different claims: the belief
    stays where the evidence left it, dependents stay shut, and the close puts the concept on the
    review ladder like any other one with evidence. Parked is a fact about *this* session; the next
    one reads the same belief and starts over with the bar back up.
    """
    known = model.nodes.get(node_id)
    if known is None:
        return False
    return known.evidence_count >= _GIVE_UP_AFTER and known.estimate < _DECAYED
