from .claim_of import claim_of
from .mastery_thresholds import DECAYED, MASTERED
from .schema import (
    ExampleBlock,
    HintBlock,
    LayoutBlock,
    LayoutSpec,
    LearnerModel,
    LessonParts,
    PracticeBlock,
    ProseBlock,
    StackBlock,
    SurfaceBlock,
)

#: Block ids. Fixed rather than generated, because a layout is compared between turns and between
#: learners — by tests, by a reviewer reading two digests side by side, and by a renderer deciding
#: what to animate. Ids that changed every turn would make two identical layouts look different.
_PROSE = "prose"
_SURFACE = "surface"
_EXAMPLE = "example"
_HINT = "hint"
_PRACTICE = "practice"

#: How many practice prompts a learner who is part-way there is given. One, not none: the scaffold
#: is sized down rather than switched off, which is what "sized to the knowledge estimate" means.
_SUPPORTED_PROMPTS = 1


def compose_layout(
    parts: LessonParts,
    *,
    node_id: str | None,
    model: LearnerModel,
) -> LayoutSpec:
    """How this turn is laid out for *this* learner — plan §8's Tier 2, in three bands.

    The claim the tier rests on is that the same concept is composed differently for two learners
    who know different amounts. Plan §8 names the three behaviours that make it true, and each one
    is read off the same number:

    | belief | worked example | hint drawer | practice |
    |---|---|---|---|
    | below ``DECAYED`` | shown, open | shown | every prompt |
    | ``DECAYED`` to ``MASTERED`` | shown, closed | shown | one prompt |
    | at or above ``MASTERED`` | absent | absent | none |

    The thresholds are the **director's own** (``mastery_thresholds``), not a second set. A learner
    the director considers to have a concept, still being scaffolded as though they did not, is the
    two rule sets disagreeing about what "has it" means — and nothing would ever look broken.

    Read off the **undecayed** estimate, which is the convention ``decide_move`` already keeps and
    states: what was *earned* is judged on the stored belief, what has *faded* on the decayed
    recall. Scaffolding is a question about what the learner has shown, so it belongs on the first
    of those. Reading the decayed value instead makes the middle band nearly unreachable — a single
    met answer lands exactly at ``DECAYED``, and one turn of decay puts it back under — so a learner
    who had just demonstrated something would be handed a beginner's lesson on the very next turn.

    Fading is answered elsewhere and better: the director *retrieves* a slipped concept, and a
    retrieval arriving with the lean layout is the point rather than an oversight — re-explaining
    what somebody is being asked to recall is the one thing that makes the move pointless
    (``select_surface`` rule 2 refuses the same substitution for the same reason).

    Deterministic, and the parameter set is what guarantees it (the same argument as
    ``select_surface``, AD18). No tutor, no grader, no client: the tutor's contribution arrives as
    ``parts``, already written, so there is no seam a model could be threaded through without this
    signature changing. What the tutor wrote is used **verbatim** — a composer that paraphrased a
    hint would be a second author nobody can see.

    ``node_id`` is ``None`` on a closing turn, which names no concept. That gets the lean layout
    rather than an exception: the goodbye is still prose and the mastery meter is still a card.

    There is deliberately no clock. Reading the undecayed belief is what removed the need for one,
    and taking it anyway would leave a parameter this cannot use — which is exactly the seam the
    determinism test exists to keep shut.
    """
    held = _held(model, node_id)

    blocks: list[LayoutBlock] = [ProseBlock(id=_PROSE)]
    if parts.worked_example is not None and held < MASTERED:
        blocks.append(
            ExampleBlock(
                id=_EXAMPLE,
                title=parts.worked_example.title,
                steps=parts.worked_example.steps,
                expanded=held < DECAYED,
            )
        )
    if (prompts := _prompts(parts, held)) is not None:
        blocks.append(PracticeBlock(id=_PRACTICE, prompts=prompts))

    # The card sits after the material that prepares it and before the hint that rescues it. Order
    # is the composition: a question placed above the worked example setting it up is a different
    # lesson built from identical parts, and a hint above the question is the answer moved up.
    blocks.append(SurfaceBlock(id=_SURFACE))
    if parts.hint is not None and held < MASTERED:
        blocks.append(HintBlock(id=_HINT, hint=parts.hint))

    return LayoutSpec(
        blocks=[
            StackBlock(id=LayoutSpec.ROOT, children=[block.id for block in blocks]),
            *blocks,
        ]
    )


def _held(model: LearnerModel, node_id: str | None) -> float:
    """What the learner has shown about this concept, undecayed. Zero when they have shown nothing.

    ``MASTERED`` for a turn that names no concept: a close is not a lesson, so the lean layout is
    the honest arrangement rather than a scaffold around a mastery meter.
    """
    if node_id is None:
        return MASTERED
    known = model.nodes.get(node_id)
    if known is None:
        return 0.0
    # A concept the learner claimed and has shown nothing about yet (P2c T3): the claim is the
    # band, or a learner who said they know this would be handed a beginner's scaffold to prove it.
    claim = claim_of(known)
    return claim if claim is not None else known.estimate


def _prompts(parts: LessonParts, held: float) -> list[str] | None:
    """How much practice this learner is given, or ``None`` for none at all.

    Taken from the front rather than sampled: ``LessonParts.practice`` is written most-useful-first,
    so a learner given fewer prompts gets the best ones rather than a random subset of them.
    """
    if not parts.practice or held >= MASTERED:
        return None
    return parts.practice if held < DECAYED else parts.practice[:_SUPPORTED_PROMPTS]
