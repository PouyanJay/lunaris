from collections.abc import Mapping
from hashlib import blake2b

from ..graph import ConceptGraph, ConceptNode, MasteryCriterion, prerequisites_of
from ..graph.schema import MasteryCriterionKind
from .recall_of import recall_of
from .schema import (
    ConceptMapCard,
    CriterionCard,
    DirectorMove,
    ExplainBack,
    LearnerModel,
    MasteryMeter,
    MeterEntry,
    MoveKind,
    QuizCard,
    SessionClock,
    SimApp,
    SimAppCard,
    SurfaceSpec,
)

#: How a quiz asks its question. One phrasing for every concept, because the variation that matters
#: is in the options — which the map authored — and a generated question would put a model back in
#: the one tier that is not allowed one (plan §8).
_QUIZ = "Which of these is actually true about {concept}?"

#: What a retrieval move asks for. Names the concept and asks for production, never recognition.
_RECALL = "Without looking back: what is {concept}, in your own words, and what is it for?"

#: The same prompt when the concept is new rather than fading. Split from ``_RECALL`` because they
#: are different requests — one asks the learner to remember, the other to articulate what they
#: have just been told — and a single wording would make the director's choice invisible to them.
_ARTICULATE = "In your own words: what is {concept}, and what would you use it for?"


def select_surface(
    move: DirectorMove,
    node: ConceptNode | None,
    *,
    graph: ConceptGraph,
    criterion: MasteryCriterion | None,
    model: LearnerModel,
    clock: SessionClock,
    sim: SimApp | None = None,
    opening_beliefs: Mapping[str, float] | None = None,
) -> SurfaceSpec:
    """Which Tier 1 component this turn shows, and every prop in it.

    A scored rule set like ``decide_move``, and for a stronger reason than symmetry: plan §8 makes
    deterministic rendering *mandatory* for this tier, because these components feed the learner
    model and a broken assessment surface corrupts data. So this takes no tutor, no grader and no
    client — there is no seam a model could be threaded through without changing this signature.

    The shared idiom is the **rule order**, not the construction. ``decide_move``'s helpers hand
    back a candidate concept and it builds every ``DirectorMove`` itself; two of the helpers here
    return the finished card, because a meter is a composition rather than a choice and the quiz
    has to be able to say "nothing to ask" by returning ``None``. Worth naming, so the resemblance
    is read as far as it goes and no further.

    Rules are tried in a fixed order, and the order IS the policy:

    1. **A close is about the session**, not a concept, so it shows what was demonstrated.
    2. **Retrieval must be produced, not recognised.** A card with options would let recognition
       stand in for recall, which is the one substitution that makes the move pointless.
    3. **A criterion that can only be demonstrated gets the simulator that demonstrates it** (T6),
       and it outranks the quiz below because the answer any card collects is graded against the
       criterion this turn staged. Showing a misconception quiz while a simulator's do-statement is
       staged would mark a picked option against a statement about driving a rate until it diverges
       — the instrument must match what is being marked. It fires only when a registry has actually
       named an application: a mounted frame with nothing in it reads as a broken session, not as a
       concept nobody has built a simulator for.
    4. **A stuck learner is shown the wrong models they might hold** — the director only remediates
       after two misses, so "can you say it" has already been asked and answered. When the concept
       authored no misconceptions there is nothing to show, and the fall-through deliberately skips
       rule 6's explain-back for the same reason: asking a stuck learner to say it back is the
       instrument that has just failed twice. They get the do-statement instead.
    5. **A concept this session cannot check gets no assessment-shaped card**, because nothing said
       next can move a belief and a card that looked like one would be lying about the turn. Rule 4
       sits above it for exactly that reason: once a simulator is mounted, something *can*.
    6. **Otherwise the criterion decides**: explain it back, or meet the do-statement as written.

    ``sim`` is a **resolved application**, never the registry that found it. That keeps the
    guarantee AD18 names: this function still takes nothing it could ask a question of, so the
    determinism of the tier remains a property of the signature rather than of what a collaborator
    happens to return today. Resolving it is the caller's job, next to the staging that produced the
    criterion it belongs to.

    Raises ``ValueError`` when a move that names a concept arrives without one. Unreachable from
    ``decide_move`` — and this is a public function anyone can call, so the alternative is handing a
    caller a mastery meter where an assessment card belonged, silently. Plan §8's whole worry is a
    broken assessment surface corrupting data; failing loudly is the cheap half of preventing it.
    """
    if move.kind is MoveKind.CLOSE:
        return _meter(graph, model, clock, opening_beliefs or {})
    if node is None:
        raise ValueError(f"a {move.kind.value} move names a concept; none was given")

    if move.kind is MoveKind.RETRIEVE:
        return ExplainBack(
            node_id=node.id, concept=node.name, prompt=_RECALL.format(concept=node.name)
        )

    # Rule 3, and it sits above the remediation quiz for a reason that is about *correctness*
    # rather than about pedagogy. Whatever card is shown, the answer it collects is graded against
    # the criterion this turn staged — so a quiz shown while a simulator's do-statement is staged
    # would have "a gradient points uphill" marked against "drive the learning rate up until the
    # loss diverges". The instrument has to match what is being marked, or the tier feeds the
    # learner model nonsense while looking perfectly reasonable on screen (plan §8).
    #
    # It also happens to be the order the plan asks for — remediation is "a modality switch (sim →
    # worked example → Feynman)" (§7) — but the ordering would be this way round regardless.
    #
    # Reachable only since T6: before a simulator could be mounted, a sim-only concept could never
    # be graded, so it could never accrue the evidence a remediation is decided from.
    if sim is not None and criterion is not None and criterion.needs_sim:
        return SimAppCard(
            node_id=node.id,
            concept=node.name,
            app_id=sim.app_id,
            url=sim.url,
            title=sim.title,
            statement=criterion.statement,
            asks=criterion.kind,
        )

    # Rule 4 is tried before rule 5's ``criterion is None`` check, which is safe because a
    # remediation target always has one: ``decide_move`` only remediates on a concept with evidence,
    # and evidence only accrues on turns that staged a criterion. Stated because that invariant
    # lives in three files — if graph editing ever mutates an existing node's criteria, or the
    # director learns to remediate on unevidenced concepts, this ordering is what breaks.
    if move.kind is MoveKind.REMEDIATE and (quiz := _quiz(node)) is not None:
        return quiz

    if criterion is None:
        return ConceptMapCard(
            focus_node_id=node.id,
            concept=node.name,
            prerequisites=_names_of(graph, prerequisites_of(graph, node.id)),
        )

    # Rule 3's fall-through, and the reason this reads ``and move.kind is not REMEDIATE``: a
    # remediation reaching here has no misconceptions to quiz on, and "say it back in your own
    # words" is precisely the instrument that has already failed twice. The do-statement below is a
    # different ask — what they will actually be marked on, stated plainly.
    if criterion.kind is MasteryCriterionKind.EXPLAIN and move.kind is not MoveKind.REMEDIATE:
        return ExplainBack(
            node_id=node.id, concept=node.name, prompt=_ARTICULATE.format(concept=node.name)
        )

    return CriterionCard(
        node_id=node.id, concept=node.name, statement=criterion.statement, asks=criterion.kind
    )


def _quiz(node: ConceptNode) -> QuizCard | None:
    """The concept's authored misconceptions with its definition among them, or ``None``.

    ``None`` when the concept has no misconceptions to offer: ``teaching_spec`` is optional by
    contract and one failed authoring call in Phase 1 leaves a concept teachable with nothing to
    quiz against, and a question with a single option is not a question.
    """
    spec = node.teaching_spec
    wrong = list(spec.misconceptions) if spec is not None else []
    # De-duplicated, because an authoring call that echoed the definition back as a misconception
    # would put the same text in twice — and then "the true one" is ambiguous by text alone, which
    # is the one thing the learner is being asked to pick out.
    options = list(dict.fromkeys([node.definition, *wrong]))
    if len(options) < 2:
        # Nothing to choose between: the concept authored no misconceptions, or the only one it
        # authored was its own definition. One guard rather than two — an earlier `if not wrong`
        # said the same thing a different way, and a second check for one reason is the shape that
        # goes stale when the reason changes.
        return None
    return QuizCard(
        node_id=node.id,
        concept=node.name,
        question=_QUIZ.format(concept=node.name),
        options=_ordered(options),
    )


def _ordered(options: list[str]) -> list[str]:
    """The options in a stable order that is not the order they were written in.

    Both halves matter. **Stable**, because a surface that reshuffled between two renders of one
    turn would be a different instrument each time it was looked at, and a learner reloading
    mid-question would find their answer pointing somewhere else. **Not the authored order**,
    because the definition is always written first here, and a truth that is always option A can be
    picked by a learner who never reads one.

    Keyed on a hash of the option's own text, which gives both: the same card always orders the same
    way, and the position of the truth varies from concept to concept because the text does. A
    random shuffle would do the second job and fail the first, which is the trade this refuses.
    """
    return sorted(options, key=lambda option: blake2b(option.encode()).digest())


def _meter(
    graph: ConceptGraph,
    model: LearnerModel,
    clock: SessionClock,
    opening_beliefs: Mapping[str, float],
) -> MasteryMeter:
    """What the learner demonstrated, in the map's own teaching order, beside where each concept
    stood when the session opened (P2c T5): movement, not a number.

    Only concepts with evidence: a meter listing every concept at zero would read as a report card
    for a course nobody enrolled in, and it would bury the part that is actually theirs.
    """
    names = {node.id: node.name for node in graph.nodes}
    return MasteryMeter(
        entries=[
            MeterEntry(
                node_id=node_id,
                concept=names.get(node_id, node_id),
                recall=recall_of(model, node_id, at_turn=clock.turn),
                evidence_count=model.nodes[node_id].evidence_count,
                recall_before=opening_beliefs.get(node_id),
            )
            for node_id in _in_teaching_order(graph, model)
        ]
    )


def _in_teaching_order(graph: ConceptGraph, model: LearnerModel) -> list[str]:
    """The concepts the learner has evidence about, ordered by the map rather than by a dict.

    Insertion order would be the order the *session* happened to touch them, which differs between
    two sittings on one map — so the same learner's meter would tell the story differently depending
    on which way the director wandered.
    """
    # Evidence only: a claim seeds a row with none (P2c T3), and a meter that showed a claimed
    # concept nothing checked as "from 70% to 0%" would be telling the learner a regression that
    # never happened (found in review).
    known = {node_id for node_id, held in model.nodes.items() if held.evidence_count > 0}
    ordered = [node_id for node_id in graph.topo_order if node_id in known]
    # Anything the order forgot still has to be shown: a meter silently missing a concept the
    # learner demonstrated is worse than one whose tail is out of order.
    return ordered + sorted(known - set(ordered))


def _names_of(graph: ConceptGraph, node_ids: list[str]) -> list[str]:
    """Concept names for ids, keeping the order given and dropping nothing silently."""
    names = {node.id: node.name for node in graph.nodes}
    return [names.get(node_id, node_id) for node_id in node_ids]
