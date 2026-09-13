from ..graph.schema import ConceptNode
from .protocols import ISimRegistry
from .schema import SimApp


def resolve_practice_sim(sims: ISimRegistry | None, node: ConceptNode) -> SimApp | None:
    """An approved practice instrument, independent of the text assessment criterion."""
    if sims is None:
        return None
    for criterion in node.mastery_criteria:
        if criterion.needs_sim:
            app = sims.app_for(node, criterion)
            if app is not None and app.contract is not None:
                return app
    return None
