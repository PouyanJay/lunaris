import asyncio
from collections.abc import AsyncIterator, Sequence

import structlog
from lunaris_runtime.resilience import build_chat_model

from ..graph.schema import ConceptNode, MasteryCriterion
from ..model_json import parse_json_object
from .ask_model import ModelCallFailedError, ModelCallTimedOutError, ask_model
from .reject_unteachable_move import reject_unteachable_move
from .review_day import review_day
from .schema import Covered, DirectorMove, LessonParts, MoveKind, WorkedExample
from .tutor_unavailable_error import TutorUnavailableError

logger = structlog.get_logger()

#: A learner is watching a cursor blink while this runs, so the ceiling is a pause in a conversation
#: rather than a batch job's patience. Past it they are better served by an error they can retry
#: than by a turn that may still be coming. Longer than C1's 15 s extension budget because this is
#: the thing they are actually waiting for, not a repair happening behind the talking.
_DEFAULT_DEADLINE_S = 30.0

#: How long the streaming path waits for the *next* fragment before calling the stream dead. Well
#: inside the whole-lesson deadline, because a stream that has stopped producing looks exactly like
#: one still thinking, and the learner is watching a cursor either way. Generous enough to cover
#: time-to-first-token, which is the longest gap a healthy stream has.
_FRAGMENT_DEADLINE_S = 15.0

_PROMPT = """You are tutoring one learner, one to one, in a live text session about "{topic}".
{learner}
The concept in front of you: {name} — {definition}
{notes}{history}
{instruction} Why now: {because}

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

#: What the illustration is bounded by. Shorter than the lesson's deadline because it runs *beside*
#: the words rather than in front of them: by the time the prose is written this has usually long
#: since answered, and anything still outstanding is trimmings the turn will go without.
_ILLUSTRATE_DEADLINE_S = 20.0

#: Bounds on what comes back. The contract caps these too — this is the near side of the same wall,
#: so an over-long field is trimmed into something usable instead of throwing the whole offer away.
_TITLE_CHARS = 200
_STEP_CHARS = 300
_HINT_CHARS = 500
_PROMPT_CHARS = 300
_MAX_STEPS = 6
_MAX_PROMPTS = 4

_ILLUSTRATE = """You are tutoring one learner, one to one, in a live text session about "{topic}".

The concept in front of you: {name} — {definition}
{notes}{history}
Alongside your explanation, prepare the supporting material for this concept. You are NOT teaching \
here and you are NOT repeating the explanation — this is what sits around it on the page.

- workedExample: one concrete instance worked through in 2 to 4 short steps. Each step is one \
sentence and does something; a step that only restates the idea is not a step.
- hint: one sentence they can uncover if they get stuck. Point at the thing people get wrong, do \
not give the answer.
- practice: 2 or 3 short prompts for them to think through. Not questions you will mark — thinking \
prompts.

{closing}

Respond with ONLY a JSON object, no prose:
{{"workedExample": {{"title": "...", "steps": ["...", "..."]}}, "hint": "...", \
"practice": ["...", "..."]}}"""

#: The close (P2c T5). The record rides the prompt as a list; the tutor may dress it, not revise it:
#: a recap that promoted a forming concept to "you've got this" would be the one moment the trace
#: and the learner disagree about what happened.
_RECAP = """You are closing a live one-to-one tutoring session about "{topic}".
{learner}
What the session covered, and how each concept stands as it ends (this is the record; say it in
your own words, warmly, but do not upgrade or downgrade any of it):
{covered}

Write what you would say to close, addressed to them directly: three to five sentences. Name what
they showed, name what is still forming and that you will pick it up first next time, and where a
concept has a review day, tell them the day. Then stop.
No headings, no bullet lists, no markdown, no questions."""

#: The practice prompts are aimed at the bar the learner is actually about to be marked against,
#: because scaffolding pointed somewhere else is scaffolding for a different question.
_PRACTICE_ON = 'The practice prompts should lead towards this, without answering it: "{statement}"'

#: When the concept stages nothing checkable, the prompts have nothing to lead towards, so they are
#: asked to lead somewhere else rather than at a bar that does not exist.
_PRACTICE_OPEN = "The practice prompts should make them look at the idea from another side."

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
        "They have met this before — earlier in this session, or before it, if they told us they "
        "know it. Do NOT re-explain it. Ask them to recall it and use it, so the remembering is "
        "theirs — that effort is the entire point of coming back, and it is how a claim gets "
        "checked."
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
        profile: str | None = None,
        run_id: str,
    ) -> str:
        prompt = _prompt_for(
            move, node, topic=topic, criterion=criterion, already_said=already_said, profile=profile
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
        profile: str | None = None,
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
            move, node, topic=topic, criterion=criterion, already_said=already_said, profile=profile
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

    async def illustrate(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> LessonParts:
        """Tier 2's material: a worked example, a hint and prompts to think through (T5, U4).

        **This can fail freely, and that is the design.** Every way it can go wrong — no provider, a
        slow one, prose where JSON was asked for, a step list of the wrong shape — comes back as
        empty ``LessonParts``, and the layout then degrades to the lesson and the card, which are on
        the turn already. So the one thing generative composition is not allowed to do is cost a
        learner their turn.

        Its own deadline, well under the lesson's, for the same reason: this runs beside the words
        rather than in front of them, so the only thing a slow illustration may spend is itself.
        """
        prompt = _ILLUSTRATE.format(
            topic=topic,
            name=node.name,
            definition=node.definition,
            notes=_notes_on(node),
            history=_history_of(already_said),
            closing=_PRACTICE_ON.format(statement=criterion.statement)
            if criterion is not None
            else _PRACTICE_OPEN,
        )
        try:
            said = await ask_model(
                self._client,
                model_name=self._model_name,
                prompt=prompt,
                deadline_s=_ILLUSTRATE_DEADLINE_S,
                on_client=self._keep,
            )
        except (ModelCallTimedOutError, ModelCallFailedError):
            # WARNING rather than INFO: the turn survives, but it survives *degraded* — the learner
            # gets the lesson without its material, and PYTHON.md puts "fallback used, degraded
            # mode entered" here. It is also the line an operator needs above the noise if a prompt
            # regression starts costing every turn its trimmings.
            logger.warning("live.tutor.illustration_skipped", run_id=run_id, node=node.id)
            return LessonParts()

        parts = _parts_from(parse_json_object(said))
        logger.info(
            "live.tutor.illustrated",
            run_id=run_id,
            node=node.id,
            move=move.kind.value,
            # What arrived, never the text itself — the same rule the lesson's own log keeps.
            example_steps=len(parts.worked_example.steps) if parts.worked_example else 0,
            hinted=parts.hint is not None,
            prompts=len(parts.practice),
        )
        return parts

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

    async def _say(
        self, prompt: str, *, run_id: str, node_id: str | None, phase: str = "lesson"
    ) -> str:
        """One bounded attempt at speaking, with every way it can fail named the same way.

        A learner cannot be left waiting because each individual retry was technically still inside
        its own budget, so the deadline wraps the whole call rather than one attempt — and whatever
        comes back out of it, the caller has exactly one failure to handle. No ``max_tokens``: the
        answer is bounded to 120 words by the prompt, which sits well inside the provider default —
        a ceiling here would only ever truncate mid-sentence.
        """
        try:
            said = await ask_model(
                self._client,
                model_name=self._model_name,
                prompt=prompt,
                deadline_s=self._deadline_s,
                on_client=self._keep,
            )
        except ModelCallTimedOutError as exc:
            logger.warning(
                "live.tutor.timed_out",
                run_id=run_id,
                node=node_id,
                phase=phase,
                deadline_s=self._deadline_s,
            )
            raise TutorUnavailableError(f"tutor timed out ({phase}, {node_id})") from exc
        except ModelCallFailedError as exc:
            logger.warning(
                "live.tutor.call_failed", run_id=run_id, node=node_id, phase=phase, exc_info=True
            )
            raise TutorUnavailableError(f"tutor could not speak ({phase}, {node_id})") from exc
        return said.strip()

    async def recap(
        self,
        topic: str,
        covered: Sequence[Covered],
        *,
        profile: str | None = None,
        run_id: str,
    ) -> str:
        """The close's words (P2c T5), over the record and only the record."""
        prompt = _RECAP.format(
            topic=topic,
            learner=_about(profile),
            covered="\n".join(
                f"- {c.concept}: {c.outcome.value}"
                + (
                    f" ({c.evidence_count} answer{'s' if c.evidence_count != 1 else ''})"
                    if c.evidence_count
                    else ""
                )
                + (f"; review due {review_day(c.due_at)}" if c.due_at is not None else "")
                for c in covered
            )
            or "- nothing: the session ended before a concept was reached",
        )
        said = await self._say(prompt, run_id=run_id, node_id=None, phase="recap")
        if not said:
            logger.warning("live.tutor.recap_empty", run_id=run_id)
            raise TutorUnavailableError("tutor wrote no recap")
        logger.info("live.tutor.recapped", run_id=run_id, covered=len(covered), chars=len(said))
        return said

    def _keep(self, client: object) -> None:
        self._client = client


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


def _parts_from(payload: dict[str, object] | None) -> LessonParts:
    """The model's answer as material, keeping whatever part of it was usable.

    Field by field rather than one ``model_validate`` of the whole object, because these three are
    independent offers: a worked example whose steps came back as a paragraph must not take the
    hint down with it. ``LessonParts`` is optional all the way through, so the salvage has somewhere
    to land, and anything that still does not fit the contract is simply not offered.

    ``None`` is what ``parse_json_object`` answers when the response was prose — the single most
    likely way this call goes wrong, and the reason the parameter is typed for it. Reached, it used
    to raise an ``AttributeError`` that the loop caught and reported as a generic failure, so the
    most ordinary outcome on this path arrived looking like a bug in Lunaris.
    """
    if payload is None:
        return LessonParts()
    return LessonParts(
        worked_example=_example_from(payload.get("workedExample")),
        hint=_one_line(payload.get("hint"), limit=_HINT_CHARS),
        practice=[
            prompt
            for raw in _listed(payload.get("practice"))[:_MAX_PROMPTS]
            if (prompt := _one_line(raw, limit=_PROMPT_CHARS)) is not None
        ],
    )


def _example_from(raw: object) -> WorkedExample | None:
    """A worked example, or nothing. Nothing when a step list came back as prose: a disclosure needs
    a body it can hide, and one long paragraph collapsed behind a title is a title."""
    if not isinstance(raw, dict):
        return None
    title = _one_line(raw.get("title"), limit=_TITLE_CHARS)
    steps = [
        step
        for value in _listed(raw.get("steps"))[:_MAX_STEPS]
        if (step := _one_line(value, limit=_STEP_CHARS)) is not None
    ]
    return WorkedExample(title=title, steps=steps) if title and steps else None


def _listed(raw: object) -> list[object]:
    """A list, or an empty one. A model answering with a bare string where an array was asked for is
    not one item — treating it as one is how a whole practice set becomes a single sentence."""
    return raw if isinstance(raw, list) else []


def _one_line(raw: object, *, limit: int) -> str | None:
    """One trimmed, bounded line of text, or nothing at all when there was none."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()[:limit]


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
    profile: str | None = None,
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
        learner=_about(profile),
        instruction=instruction,
        # The director's own reason, so the tutor knows *why* this move now — a retrieval of a
        # concept the learner claimed reads nothing like one of a concept that is fading (P2c T3).
        because=move.reason,
        closing=_STAGE.format(statement=criterion.statement) if criterion else _OPEN_ENDED,
    )


#: Who the learner is, when the placement interview said (P2c T3). Kept short in the prompt: it is
#: context for the examples the tutor reaches for, not a brief to be recited back.
_ABOUT = "\nAbout this learner, in their own words from a short interview: {profile}\n"


def _about(profile: str | None) -> str:
    return _ABOUT.format(profile=profile.strip()[:600]) if profile and profile.strip() else ""


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
