import re
from collections.abc import AsyncIterator, Sequence

from ..graph.schema import ConceptNode, MasteryCriterion
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

#: The staged do-statement, asked plainly. The offline path has to put a real question in front of
#: the learner or nothing downstream — the grader, the belief, the director's next move — can be
#: exercised without a provider.
_ASK = " So: {statement}"

#: Opens a turn the tutor has already spoken on. The offline path has to be able to *show* that a
#: second pass over one concept is not the first pass repeated, or a surface — and a review — could
#: pass over a tutor that says the same thing forever.
_AGAIN = "Another way to see it. "

#: How the offline path breaks a lesson into fragments: on word boundaries, keeping the whitespace,
#: so the pieces re-join to exactly what ``teach`` said. A model streams in tokens rather than
#: words, and the surface must not care which — a client that only renders correctly on one of the
#: two chunkings is a client that will break the first time a provider changes its tokenizer.
_FRAGMENTS = re.compile(r"\S+\s*")


class StubTutor:
    """A tutor that needs no model, no key and no network.

    Not lorem: it teaches the concept it was handed, in words that differ by move, and it surfaces
    the misconception the node names. That is what lets the offline path stand in for the real one
    in CI and keyless dev — a fixed string would let the whole session be wired to the wrong node,
    or ignore the director entirely, without a single test noticing.
    """

    async def teach(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        run_id: str,
    ) -> str:
        return self._lesson(move, node, criterion=criterion, already_said=already_said)

    async def stream(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        run_id: str,
    ) -> AsyncIterator[str]:
        """The same lesson, word by word.

        Genuinely fragmented rather than yielded whole: the offline path is what CI, keyless dev and
        every review of the live surface actually see, so a stub that handed over one piece would
        let a surface that cannot assemble deltas pass every test we have.
        """
        lesson = self._lesson(move, node, criterion=criterion, already_said=already_said)
        for fragment in _FRAGMENTS.findall(lesson):
            yield fragment

    def _lesson(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        criterion: MasteryCriterion | None,
        already_said: Sequence[str],
    ) -> str:
        """What this tutor says about this move, whole. One source for both paths, so the words a
        learner streams and the words a learner re-reads cannot come apart."""
        script = _SCRIPT.get(move.kind)
        if script is None:
            reject_unteachable_move(move.kind)

        said = script.format(name=node.name, definition=node.definition)
        if already_said:
            said = _AGAIN + said
        misconceptions = node.teaching_spec.misconceptions if node.teaching_spec else []
        if misconceptions:
            said += _WATCH_FOR.format(misconception=misconceptions[0])
        if criterion is not None:
            said += _ASK.format(statement=criterion.statement)
        return said
