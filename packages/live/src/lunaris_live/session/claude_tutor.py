import asyncio

import structlog
from lunaris_runtime.resilience import build_chat_model, retry_on_transient

from ..graph.schema import ConceptNode
from .reject_unteachable_move import reject_unteachable_move
from .schema import DirectorMove, MoveKind
from .tutor_unavailable_error import TutorUnavailableError

logger = structlog.get_logger()

#: A learner is watching a cursor blink while this runs, so the ceiling is a pause in a conversation
#: rather than a batch job's patience. Past it they are better served by an error they can retry
#: than by a turn that may still be coming. Longer than C1's 15 s extension budget because this is
#: the thing they are actually waiting for, not a repair happening behind the talking.
_DEFAULT_DEADLINE_S = 30.0

#: Matches the compiler's: three attempts inside a four-second ceiling survives a dropped socket
#: without eating the deadline above. The library defaults (eight attempts, thirty seconds) are
#: sized for a batch job and would turn a fast clean failure into a slow cancelled one.
_TRANSIENT_ATTEMPTS = 3
_TRANSIENT_MAX_DELAY_S = 4.0

_PROMPT = """You are tutoring one learner, one to one, in a live text session about "{topic}".

The concept in front of you: {name} — {definition}
{notes}
{instruction}

Write only what you would say to them next, in your own voice, addressed to them directly. Under \
120 words. No headings, no bullet lists, no markdown. Finish with one question that makes them \
think, not one they can answer with yes."""

#: What the move means for the person speaking. The director's whole output is the move, so a tutor
#: that ignored it would make the policy decorative: the trace would record adaptation the learner
#: never heard.
_INSTRUCTION: dict[MoveKind, str] = {
    MoveKind.INTRODUCE: (
        "This concept is new to them. Start from something concrete they already have, then the "
        "idea itself. Where one of the wrong models above fits, teach past it — do not announce it "
        "back at them as a mistake they have not made yet."
    ),
    MoveKind.RETRIEVE: (
        "They met this earlier and it is fading. Do NOT re-explain it. Ask them to recall it and "
        "use it, so the remembering is theirs — that effort is the entire point of coming back."
    ),
    MoveKind.REMEDIATE: (
        "They have been taught this and it has not landed. Do NOT repeat the explanation they have "
        "already heard — come at it a different way: a different example, a different "
        "representation, a smaller step. Assume one of the wrong models above is what they are "
        "holding, and go after it."
    ),
}


class ClaudeTutor:
    """Teaches one director move with Claude, over the concept's own authored notes.

    One call per turn, and the concept's ``teaching_spec`` is most of the prompt. Phase 1 spends a
    model call per concept authoring misconceptions "as the learner would believe them" for exactly
    this moment: a tutor that only knows what is true explains into the air, while one that knows
    how people usually get this wrong can go after the specific wrong model in front of it. Passing
    them verbatim rather than summarised is what keeps the two halves of the product in agreement.

    Unlike the compiler, this cannot degrade. A compile that loses one concept's notes still hands
    back a map; a turn with no words is not a turn, so a failure here is a failure (A2 —
    ``SessionTurn.tutor`` is ``min_length=1``, and a turn the learner cannot see is a decision that
    happened to them invisibly).
    """

    def __init__(
        self,
        model_name: str,
        *,
        client: object | None = None,
        deadline_s: float = _DEFAULT_DEADLINE_S,
    ) -> None:
        self._model_name = model_name
        # Injected in tests; production leaves it None so the client is built on first use and
        # constructing the tutor needs no API key.
        self._client = client
        self._deadline_s = deadline_s

    async def teach(self, move: DirectorMove, node: ConceptNode, *, topic: str, run_id: str) -> str:
        instruction = _INSTRUCTION.get(move.kind)
        if instruction is None:
            reject_unteachable_move(move.kind)

        prompt = _PROMPT.format(
            topic=topic,
            name=node.name,
            definition=node.definition,
            notes=_notes_on(node),
            instruction=instruction,
        )
        said = await self._say(prompt, run_id=run_id, node_id=node.id)

        if not said:
            # Caught here, where it can still be named, rather than as a validation error thrown
            # from inside session assembly with nothing to say about which turn produced it.
            logger.warning("live.tutor.said_nothing", run_id=run_id, node=node.id)
            raise TutorUnavailableError(f"tutor returned nothing for {node.id}")

        logger.info(
            "live.tutor.taught",
            run_id=run_id,
            node=node.id,
            move=move.kind.value,
            # Length rather than the text: operational logs are for debugging, and a transcript of
            # somebody being taught is not something to scatter through them.
            chars=len(said),
        )
        return said

    async def _say(self, prompt: str, *, run_id: str, node_id: str) -> str:
        """One bounded attempt at speaking, with every way it can fail named the same way.

        A learner cannot be left waiting because each individual retry was technically still inside
        its own budget, so the deadline wraps the whole call rather than one attempt — and whatever
        comes back out of it, the caller has exactly one failure to handle.
        """
        try:
            async with asyncio.timeout(self._deadline_s):
                return await self._ask(prompt)
        except TimeoutError as exc:
            logger.warning(
                "live.tutor.timed_out", run_id=run_id, node=node_id, deadline_s=self._deadline_s
            )
            raise TutorUnavailableError(f"tutor timed out on {node_id}") from exc
        except Exception as exc:
            logger.warning("live.tutor.call_failed", run_id=run_id, node=node_id, exc_info=True)
            raise TutorUnavailableError(f"tutor could not teach {node_id}") from exc

    async def _ask(self, prompt: str) -> str:
        if self._client is None:
            # No ``max_tokens``: the answer is bounded to 120 words by the prompt, which sits well
            # inside the provider default — a ceiling here would only ever truncate mid-sentence.
            self._client = build_chat_model(self._model_name)
        message = await retry_on_transient(
            lambda: self._client.ainvoke(prompt),  # type: ignore[attr-defined]
            max_attempts=_TRANSIENT_ATTEMPTS,
            max_delay_s=_TRANSIENT_MAX_DELAY_S,
        )
        content = message.content
        return (content if isinstance(content, str) else str(content)).strip()


def _notes_on(node: ConceptNode) -> str:
    """The concept's teaching notes as the tutor reads them, or nothing at all.

    ``teaching_spec`` is optional by contract: one failed authoring call in Phase 1 leaves a concept
    teachable-in-principle, and a tutor that refused it would turn a degraded compile into an
    unteachable map. So an unspecified concept is taught from its definition alone, which is worse
    teaching and still teaching.
    """
    spec = node.teaching_spec
    if spec is None:
        return ""

    lines = [f"What they should be able to do with it: {spec.objective}"]
    if spec.misconceptions:
        lines.append(
            "Wrong models people commonly hold about this, written as the learner would believe "
            "them:"
        )
        lines.extend(f"- {misconception}" for misconception in spec.misconceptions)
    lines.append(f"Teaching stance: {spec.depth.value}")
    return "\n".join(lines) + "\n"
