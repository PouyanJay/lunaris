from ..graph.schema import ConceptNode, MasteryCriterion


def stage_criterion(node: ConceptNode) -> MasteryCriterion | None:
    """The do-statement a text session can actually put in front of the learner, if there is one.

    Criteria marked ``needs_sim`` are skipped rather than asked in prose: they exist to be
    demonstrated in an interactive simulator (Phase 3), and asking somebody to *describe* driving a
    rate up until it diverges grades their imagination instead of the thing the criterion names.

    ``None`` is a real answer — a concept whose every criterion needs a simulator can be taught here
    and cannot be checked here. That is honest, and it is what tells Phase 3 which sims to build
    first.
    """
    return next((c for c in node.mastery_criteria if not c.needs_sim), None)
