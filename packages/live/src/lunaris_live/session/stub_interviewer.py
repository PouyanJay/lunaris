from collections.abc import Sequence

from .schema import InterviewExchange

#: What the plan says the interview is for (§6): background, prior exposure, and what the learner
#: wants to build with this. One question per, in that order, each naming the topic so a session
#: wired to the wrong one is visible rather than plausible.
_QUESTIONS: tuple[str, ...] = (
    "Before we start on {topic}: what have you already met of it, and where?",
    "What would you like to be able to do with {topic} once we're done?",
    "Is there a part of {topic} that has never quite made sense to you?",
)


class StubInterviewer:
    """An interviewer that needs no model, no key and no network.

    Asks the plan's three questions in order and then stops. Real enough for the offline path to
    carry a whole placement — a surface, and a review, can see the interview open, continue and
    close without a provider — and no more: it never reads the answers, because reading them well
    is exactly the model's job.
    """

    async def ask(
        self,
        topic: str,
        *,
        exchanges: Sequence[InterviewExchange] = (),
        run_id: str,
    ) -> str | None:
        if len(exchanges) >= len(_QUESTIONS):
            return None
        return _QUESTIONS[len(exchanges)].format(topic=topic)
