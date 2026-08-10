from ..graph.schema import ConceptNode
from .reject_unteachable_move import reject_unteachable_move
from .schema import DirectorMove, MoveKind

#: One phrasing per move, because a stub that said the same thing for every move would let a
#: surface be built — and reviewed, and shipped — against a session that never appeared to adapt.
#: Each names the concept, so a session wired to the wrong node is visible rather than plausible.
_SCRIPT: dict[MoveKind, str] = {
    MoveKind.INTRODUCE: "Let's start with {name}. {definition}",
    MoveKind.RETRIEVE: (
        "Before we go on, bring {name} back to mind: what was it, in your own words?"
    ),
    MoveKind.REMEDIATE: (
        "{name} hasn't landed yet, so let's come at it a different way. {definition}"
    ),
}

#: Appended when the concept names one. The offline path exercises the same claim the keyed one
#: does — that a node's authored notes reach the learner — and it is the only place the API suite
#: can prove it, since the API suite has no provider.
_WATCH_FOR = " A lot of people think {misconception} Worth watching for."


class StubTutor:
    """A tutor that needs no model, no key and no network.

    Not lorem: it teaches the concept it was handed, in words that differ by move, and it surfaces
    the misconception the node names. That is what lets the offline path stand in for the real one
    in CI and keyless dev — a fixed string would let the whole session be wired to the wrong node,
    or ignore the director entirely, without a single test noticing.
    """

    async def teach(self, move: DirectorMove, node: ConceptNode, *, topic: str, run_id: str) -> str:
        script = _SCRIPT.get(move.kind)
        if script is None:
            reject_unteachable_move(move.kind)

        said = script.format(name=node.name, definition=node.definition)
        misconceptions = node.teaching_spec.misconceptions if node.teaching_spec else []
        if misconceptions:
            said += _WATCH_FOR.format(misconception=misconceptions[0])
        return said
