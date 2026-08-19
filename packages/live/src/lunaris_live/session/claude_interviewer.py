import asyncio
from collections.abc import Sequence

import structlog
from lunaris_runtime.resilience import build_chat_model, retry_on_transient

from ..model_json import parse_json_object
from .interviewer_unavailable_error import InterviewerUnavailableError
from .schema import InterviewExchange

logger = structlog.get_logger()

#: A question is short and the learner is waiting on it, so this is tighter than the tutor's 30 s
#: and much tighter than a compile's: past it the loop ends the interview rather than the turn.
_DEFAULT_DEADLINE_S = 20.0

#: Matches the tutor's and the compiler's: three attempts inside a four-second ceiling survives a
#: dropped socket and cannot outlive the deadline above.
_TRANSIENT_ATTEMPTS = 3
_TRANSIENT_MAX_DELAY_S = 4.0

_PROMPT = """You are opening a one-to-one tutoring session on "{topic}".

While a map of the subject is being built in the background (about a minute), you are getting to
know the learner, so that the teaching can start where they actually are. You want, in roughly this
order: what they have already met of "{topic}" and where; what they want to be able to DO with it;
and anything about it that has never quite made sense to them.

Rules:
- Ask ONE short question at a time, warm and plain, under 40 words. Never teach, never quiz, never
  explain the subject; you are listening, not testing.
- Read what they have said so far and build on it; do not repeat a question they have answered.
- Three to five exchanges is plenty. When you have enough to place them, finish.

Exchanged so far, oldest first:
{exchanges}

Answer with JSON only, one object:
  {{"question": "<the next question, or an empty string when finishing>", "done": <true|false>}}
"""

_NOTHING_YET = "(nothing yet: this is the opening question)"


class ClaudeInterviewer:
    """Runs the placement conversation with Claude (P2c T2).

    Its whole job is to listen well: the exchange history rides the prompt verbatim, and its
    answer is a question or an explicit end, never prose the loop then has to guess at. Runs on
    the tutor's tier (A3): the interview is the first thing a learner reads, and the words have to
    be good.

    Every way it fails is ``InterviewerUnavailableError``, which the loop degrades to "the interview
    is over" rather than to a failed turn — a nicety must not cost the answer the learner just gave.
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
        # constructing the interviewer needs no API key.
        self._client = client
        self._deadline_s = deadline_s

    async def ask(
        self,
        topic: str,
        *,
        exchanges: Sequence[InterviewExchange] = (),
        run_id: str,
    ) -> str | None:
        prompt = _PROMPT.format(topic=topic, exchanges=_history(exchanges))
        payload = parse_json_object(await self._say(prompt, run_id=run_id))
        if payload is None or not isinstance(payload.get("done"), bool):
            logger.warning("live.interviewer.answer_unusable", run_id=run_id)
            raise InterviewerUnavailableError("interviewer answered with no usable JSON")
        if payload["done"]:
            logger.info("live.interviewer.done", run_id=run_id, exchanges=len(exchanges))
            return None
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            # A blank question would be stored as a turn the learner cannot read
            # (``SessionTurn.tutor`` is ``min_length=1``); refused here, where it can be named.
            logger.warning("live.interviewer.asked_nothing", run_id=run_id)
            raise InterviewerUnavailableError("interviewer asked nothing")
        logger.info("live.interviewer.asked", run_id=run_id, exchanges=len(exchanges))
        return question.strip()

    async def _say(self, prompt: str, *, run_id: str) -> str:
        """One bounded attempt, with every way it can fail named the same way."""
        try:
            async with asyncio.timeout(self._deadline_s):
                if self._client is None:
                    self._client = build_chat_model(self._model_name)
                message = await retry_on_transient(
                    lambda: self._client.ainvoke(prompt),  # type: ignore[attr-defined]
                    max_attempts=_TRANSIENT_ATTEMPTS,
                    max_delay_s=_TRANSIENT_MAX_DELAY_S,
                )
        except TimeoutError as exc:
            logger.warning("live.interviewer.timed_out", run_id=run_id, deadline_s=self._deadline_s)
            raise InterviewerUnavailableError("interviewer timed out") from exc
        except Exception as exc:
            logger.warning("live.interviewer.call_failed", run_id=run_id, exc_info=True)
            raise InterviewerUnavailableError("interviewer could not ask") from exc
        content = getattr(message, "content", "")
        return content if isinstance(content, str) else str(content)


def _history(exchanges: Sequence[InterviewExchange]) -> str:
    if not exchanges:
        return _NOTHING_YET
    return "\n".join(f"Q: {e.question}\nA: {e.answer}" for e in exchanges)
