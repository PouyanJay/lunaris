from ..graph.schema import ConceptNode, MasteryCriterion
from .protocols import ISimRegistry


def stage_criterion(
    node: ConceptNode, *, sims: ISimRegistry | None = None
) -> MasteryCriterion | None:
    """The do-statement this turn can actually put in front of the learner, if there is one.

    **Prose first, always.** A criterion a learner can answer in their own words is graded by the
    separate grader against the statement it names (U1), which is the evidence path this product has
    actually evaluated. Routing around it because a simulator happens to exist would trade a
    measured instrument for an unmeasured one.

    **Then a simulator, if one is registered** (T6). Criteria marked ``needs_sim`` exist to be
    demonstrated rather than described — asking somebody to *describe* driving a rate up until it
    diverges grades their imagination instead of the thing the criterion names — so they are staged
    only when there is somewhere for the learner to do it.

    ``None`` is still a real answer, and it is the ordinary one: a concept whose every criterion
    needs a simulator nobody has built yet can be taught here and cannot be checked here. That is
    honest, and it is what tells Phase 3 which sims to build first.
    """
    spoken = next((c for c in node.mastery_criteria if not c.needs_sim), None)
    if spoken is not None or sims is None:
        return spoken

    # The first criterion the registry can actually serve. Asking per criterion rather than per
    # concept because a concept can name several, and Phase 3's registry will know about some of
    # them before it knows about the rest.
    return next(
        (c for c in node.mastery_criteria if c.needs_sim and sims.app_for(node, c) is not None),
        None,
    )
