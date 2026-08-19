from ..graph.schema import ConceptNode, MasteryCriterion
from .protocols import ISimRegistry
from .schema import SimApp


def resolve_sim_app(
    sims: ISimRegistry | None, node: ConceptNode, staged: MasteryCriterion | None
) -> SimApp | None:
    """The simulator this turn mounts, if any (T6).

    Its own function because it is called from both entry points into the loop and must answer the
    same way in each: the mount a learner meets when a session opens and the mount they meet three
    turns in are the same decision, and two copies of it are two things to keep in step by hand.

    Resolved here, beside the staging that produced ``staged``, rather than inside
    ``select_surface`` — that function takes a *resolved* application and nothing it could ask a
    question of, which is what keeps the tier's determinism a property of its signature (AD18).

    ``None`` whenever the deployment registers no simulators (the default), the turn staged
    nothing, or the registry has nothing for this criterion. A criterion that needs a simulator is
    only ever staged when one was found, so in practice this re-asks a question already answered —
    deliberately, because the two are resolved by different calls, and a card naming no application
    would mount an empty frame in front of a learner asked to demonstrate something in it.
    """
    if sims is None or staged is None:
        return None
    return sims.app_for(node, staged)
