import asyncio
from collections.abc import AsyncIterator, Sequence

import structlog
from lunaris_runtime.resilience import build_chat_model, retry_on_transient

from ..graph.schema import ConceptNode, MasteryCriterion
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

#: How long the streaming path waits for the *next* fragment before calling the stream dead. Well
#: inside the whole-lesson deadline, because a stream that has stopped producing looks exactly like
#: one still thinking, and the learner is watching a cursor either way. Generous enough to cover
#: time-to-first-token, which is the longest gap a healthy stream has.
_FRAGMENT_DEADLINE_S = 15.0

_PROMPT = """You are tutoring one learner, one to one, in a live text session about "{topic}".

The concept in front of you: {name} — {definition}
{notes}{history}
{instruction}

Write only what you would say to them next, in your own voice, addressed to them directly. Under \
120 words. No headings, no bullet lists, no markdown. {closing}"""

#: How a turn ends. The staged form is U1's whole mechanism: the tutor asks for the concept's own
#: do-statement, the learner answers in prose, and a separate grader scores that answer against that
#: statement. Asked in the tutor's words rather than pasted, because a do-statement is written for
#: the system ("Say which way a weight should move") and a question is written for a person.
_STAGE = (
    'End by asking them to do exactly this, in your own words, as a question: "{statement}" '
    "Ask for it directly — this is what they will be marked on, so a question they could answer "
    "without doing it would mark them on nothing."
)

#: When the concept has nothing a text session can check (every criterion needs a simulator), the
#: turn still has to end somewhere. Nothing the learner says next can move a belief, so this asks
#: for thought rather than for evidence.
_OPEN_ENDED = "Finish with one question that makes them think, not one they can answer with yes."

#: What this tutor has already said to this learner about this concept. Passed verbatim, because
#: the instruction is not to avoid the topic but to avoid the *words and the analogy* — a
#: remediation that reopens with the same hillside is the same explanation in a different order.
_ALREADY_SAID = """
You have ALREADY said this to them, word for word, earlier in this session:
{said}
Do not repeat it and do not re-use its analogy or its example. They have heard it and it did not \
land; saying it again more slowly is the one thing that cannot work.
"""

#: How much of the history to carry. The last two turns on a concept is what a remediation needs to
#: avoid repeating itself; the whole session would be most of the prompt and most of the cost.
_HISTORY_DEPTH = 2
_HISTORY_CHARS = 600

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
        prompt = _prompt_for(
            move, node, topic=topic, criterion=criterion, already_said=already_said
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
        """The same lesson, handed over as the model writes it (P2b A2).

        Not retried, and that is the difference from ``teach`` rather than an omission. Once a
        fragment has been yielded the learner has read it, so a second attempt would either repeat
        words they are looking at or contradict them — a whole answer can be thrown away and asked
        for again, and a partly-read one cannot. A stream that dies is therefore a failed turn, and
        the caller offers a retry that means something because nothing has been persisted yet.
        """
        prompt = _prompt_for(
            move, node, topic=topic, criterion=criterion, already_said=already_said
        )
        said = 0
        async for fragment in self._fragments(prompt, run_id=run_id, node_id=node.id):
            # A model often opens with whitespace, and ``teach`` strips it. Doing the same to the
            # first words the learner sees keeps the two paths saying the same thing — and stops a
            # surface having to trim text it is rendering one fragment at a time.
            opening = fragment.lstrip() if said == 0 else fragment
            if not opening:
                continue
            said += len(opening)
            yield opening

        if said == 0:
            # Same failure as a tutor that answered with nothing, for the same reason:
            # ``SessionTurn.tutor`` is ``min_length=1``, and a wordless turn cannot be stored.
            logger.warning("live.tutor.streamed_nothing", run_id=run_id, node=node.id)
            raise TutorUnavailableError(f"tutor streamed nothing for {node.id}")

        logger.info(
            "live.tutor.taught", run_id=run_id, node=node.id, move=move.kind.value, chars=said
        )

    async def _fragments(self, prompt: str, *, run_id: str, node_id: str) -> AsyncIterator[str]:
        """The model's own fragments, bounded twice, with every failure named one way.

        Two deadlines because they catch different deaths. ``_FRAGMENT_DEADLINE_S`` bounds the wait
        for the *next* fragment — a stream that has silently stopped producing looks identical to
        one still thinking, and only a clock can tell them apart. ``deadline_s`` bounds the whole
        lesson, so a model trickling one token at a time cannot hold a learner past the budget by
        never quite going quiet.

        The per-fragment timeout lives in ``_next_chunk`` and wraps the ``anext`` alone, never a
        ``yield``. A timeout that could fire while this generator is suspended would deliver its
        cancellation into whatever the *consumer* happened to be awaiting, which is a failure with
        no relationship to the tutor at all — which is most of why the read is its own function.
        """
        started = asyncio.get_running_loop().time()
        if self._client is None:
            self._client = build_chat_model(self._model_name)
        chunks = self._client.astream(prompt)  # type: ignore[attr-defined]
        try:
            while (chunk := await _next_chunk(chunks, run_id=run_id, node_id=node_id)) is not None:
                if asyncio.get_running_loop().time() - started > self._deadline_s:
                    logger.warning(
                        "live.tutor.timed_out",
                        run_id=run_id,
                        node=node_id,
                        deadline_s=self._deadline_s,
                    )
                    raise TutorUnavailableError(f"tutor timed out on {node_id}")
                yield _text_of(chunk)
        finally:
            # The provider's stream holds a socket, and abandoning this generator part-way — the
            # learner closed the tab — would otherwise leave it open until the client was collected.
            await getattr(chunks, "aclose", _nothing_to_close)()

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
        return _text_of(message).strip()


async def _next_chunk(chunks: AsyncIterator[object], *, run_id: str, node_id: str) -> object | None:
    """One chunk from the model, bounded, with every way it can fail named the same way.

    ``None`` means the stream ended. Anything else — a stall, a dropped socket, a provider error —
    comes back as ``TutorUnavailableError``, so the generator above has one failure to think about
    and can be read as a loop rather than as exception handling with a loop inside it.

    The ``asyncio.timeout`` is here rather than around the caller's loop precisely so it can only
    fire while this ``anext`` is awaited. Wrapped around a body containing a ``yield``, it would be
    live while the *consumer* was running and would cancel whatever that happened to be doing.
    """
    try:
        async with asyncio.timeout(_FRAGMENT_DEADLINE_S):
            return await anext(chunks, None)
    except TimeoutError as exc:
        logger.warning("live.tutor.stream_stalled", run_id=run_id, node=node_id)
        raise TutorUnavailableError(f"tutor stopped mid-answer on {node_id}") from exc
    except Exception as exc:
        logger.warning("live.tutor.stream_failed", run_id=run_id, node=node_id, exc_info=True)
        raise TutorUnavailableError(f"tutor could not teach {node_id}") from exc


async def _nothing_to_close() -> None:
    """Stand-in for a stream that has no ``aclose`` — a hand-rolled async iterator in a test."""


def _text_of(message: object) -> str:
    """The words in a message or a chunk. ``content`` is typed loosely by the provider (a string,
    or a list of content blocks), and one place to normalise it is what stops the streaming and
    whole paths disagreeing about what "what the model said" means."""
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content)


def _prompt_for(
    move: DirectorMove,
    node: ConceptNode,
    *,
    topic: str,
    criterion: MasteryCriterion | None,
    already_said: Sequence[str],
) -> str:
    """What the tutor is asked, for either way of answering.

    Shared by ``teach`` and ``stream`` rather than duplicated: the two paths exist to differ in
    *delivery*, and a prompt that drifted between them would make the live surface and the stored
    transcript two different lessons — which is exactly the divergence ``ITutor`` promises against.
    """
    instruction = _INSTRUCTION.get(move.kind)
    if instruction is None:
        reject_unteachable_move(move.kind)

    return _PROMPT.format(
        topic=topic,
        name=node.name,
        definition=node.definition,
        notes=_notes_on(node),
        history=_history_of(already_said),
        instruction=instruction,
        closing=_STAGE.format(statement=criterion.statement) if criterion else _OPEN_ENDED,
    )


def _history_of(already_said: Sequence[str]) -> str:
    """What the tutor has already told this learner about this concept, or nothing at all."""
    recent = [said.strip() for said in already_said if said.strip()][-_HISTORY_DEPTH:]
    if not recent:
        return ""
    return _ALREADY_SAID.format(said="\n\n".join(f'"{said[:_HISTORY_CHARS]}"' for said in recent))


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
