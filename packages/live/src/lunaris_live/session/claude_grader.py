from collections.abc import Sequence

import structlog

from ..graph.schema import ConceptNode, MasteryCriterion
from ..model_json import parse_json_object
from .ask_model import ModelCallFailedError, ModelCallTimedOutError, ask_model
from .grader_unavailable_error import GraderUnavailableError
from .max_answer_chars import MAX_ANSWER_CHARS
from .schema import EvidenceKind, PriorAttempt, TurnGrade

logger = structlog.get_logger()

#: Shorter than the tutor's: this is one classification of one answer, and the learner is sitting on
#: the other side of it waiting to find out whether they were right.
_DEFAULT_DEADLINE_S = 20.0

_PROMPT = """You are marking one answer from a learner in a live tutoring session. Judge ONLY \
whether they met the specific bar below — not whether the answer is impressive, well written, or \
says something else true about the topic.

The concept: {name} — {definition}
What they were asked to do: {statement}
What they said: "{answer}"

Judge it as one of:
- "met" — they did the thing that was asked, in substance. Wording, length and polish do not matter.
- "partial" — the right idea is there but incomplete, or right for the wrong reason.
- "not_met" — they did not do it, said they do not know, or got it wrong.

Be strict about the bar and generous about the phrasing: a learner explaining it in their own \
clumsy words has met it, and a learner restating the question in fluent words has not.

Respond with ONLY a JSON object, no prose:
{{"verdict": "met", "reason": "One sentence, addressed to the learner, saying what they did or \
missed."}}"""

#: The prompt when the learner has already had a go at this same bar (T8).
#:
#: The rule it adds is monotonicity, and it is there because the first real session broke it: an
#: answer was marked partial and told it was missing "adjusts many small numbers (weights)", a later
#: answer said exactly that, and it was marked NOT met for "restating the definition". A grader that
#: scores a learner lower for following its own feedback teaches them to stop reading it.
#:
#: Their earlier words, never the earlier *reasons*: feeding a model its own prose back is how a
#: grader talks itself into a position rather than re-reading the answer in front of it.
_PROMPT_WITH_HISTORY = (
    _PROMPT
    + """

What they have already tried at this same bar, oldest first:
{previously}

Two rules about that history, and they matter more than anything else here:
- An answer that says everything an earlier one said, plus more, must NEVER be scored lower than \
that earlier answer was. If they added what they were told was missing, that is progress and it is \
scored as progress.
- Judge THIS answer against the bar, not against how many goes it has taken. A learner who gets \
there on the fourth attempt has got there."""
)

#: What the grader is allowed to have decided. An unrecognised verdict is refused rather than
#: coerced: the belief this moves is what the director gates progress on, so guessing which side of
#: the line "mostly" falls on is guessing with somebody's curriculum.
_VERDICTS = {kind.value: kind for kind in EvidenceKind}


def _history(previously: Sequence[PriorAttempt]) -> str:
    """The learner's earlier goes at this bar, oldest first, one per line.

    Their words and the verdict, never the earlier reason (see ``PriorAttempt``). Each answer is
    bounded the same way the current one is: it reached the prompt as learner input once already,
    and a history of four unbounded answers is four times the exposure.
    """
    return "\n".join(
        f'- "{attempt.answer.strip()[:MAX_ANSWER_CHARS]}" → {attempt.kind.value}'
        for attempt in previously
    )


class ClaudeGrader:
    """Scores an answer against one staged criterion with Claude.

    Runs on the worker tier (A1): teaching is the quality surface, while judging one answer against
    one explicit do-statement is a classification. Revisit if the simulated-learner eval (T9) shows
    the grader is the weak link — it is the one component whose mistakes compound, since every
    verdict it gets wrong is written into a belief the director then acts on for the rest of the
    session.
    """

    def __init__(
        self,
        model_name: str,
        *,
        client: object | None = None,
        deadline_s: float = _DEFAULT_DEADLINE_S,
    ) -> None:
        self._model_name = model_name
        self._client = client
        self._deadline_s = deadline_s

    async def grade(
        self,
        answer: str,
        *,
        criterion: MasteryCriterion,
        node: ConceptNode,
        run_id: str,
        previously: Sequence[PriorAttempt] = (),
    ) -> TurnGrade:
        # Two prompts rather than one with an empty history: "here is what they tried before:
        # nothing" invites a model to reason about an absence, and the first attempt at any bar is
        # the common case (T8).
        template = _PROMPT_WITH_HISTORY if previously else _PROMPT
        prompt = template.format(
            name=node.name,
            definition=node.definition,
            statement=criterion.statement,
            # Bounded here rather than trusted: the answer is learner input arriving at a model
            # prompt, and an unbounded one would be a cost and a truncation risk at once.
            answer=answer.strip()[:MAX_ANSWER_CHARS],
            previously=_history(previously),
        )
        payload = parse_json_object(await self._ask(prompt, run_id=run_id, node_id=node.id))

        verdict = _VERDICTS.get(str(payload.get("verdict"))) if payload else None
        if verdict is None:
            logger.warning(
                "live.grader.verdict_unusable",
                run_id=run_id,
                node=node.id,
                verdict=str(payload.get("verdict"))[:40] if payload else None,
            )
            raise GraderUnavailableError(f"grader returned no usable verdict for {node.id}")

        reason = payload.get("reason")
        logger.info("live.grader.graded", run_id=run_id, node=node.id, verdict=verdict.value)
        return TurnGrade(
            kind=verdict,
            # A verdict with no words is still a usable verdict — the belief moves either way — so
            # a missing reason degrades to a plain one rather than throwing the grade away.
            reason=(reason.strip()[:500] if isinstance(reason, str) and reason.strip() else "—"),
        )

    async def _ask(self, prompt: str, *, run_id: str, node_id: str) -> str:
        try:
            return await ask_model(
                self._client,
                model_name=self._model_name,
                prompt=prompt,
                deadline_s=self._deadline_s,
                on_client=self._keep,
            )
        except ModelCallTimedOutError as exc:
            logger.warning(
                "live.grader.timed_out", run_id=run_id, node=node_id, deadline_s=self._deadline_s
            )
            raise GraderUnavailableError(f"grader timed out on {node_id}") from exc
        except ModelCallFailedError as exc:
            logger.warning("live.grader.call_failed", run_id=run_id, node=node_id, exc_info=True)
            raise GraderUnavailableError(f"grader could not score {node_id}") from exc

    def _keep(self, client: object) -> None:
        self._client = client
