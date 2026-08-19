"""How a Live session failure becomes an HTTP answer.

Its own module because **both** of the session plane's entry points need it: the REST router and
Phase 2b's AG-UI stream. Leaving it on one of them would make the other import a module about
somebody else's transport, and would give ``router.py`` a second public export — the same reasoning
that put ``LiveWorkRefusedError`` in ``live/work_refused.py`` rather than in whichever plane raised
it first.

The sentence a learner reads must not depend on whether their client speaks REST or AG-UI.
"""

import structlog
from fastapi import HTTPException, status
from lunaris_live.session import (
    GraderUnavailableError,
    PlacementNotAnswerableError,
    SessionClosedError,
    SessionFormatError,
    StaleAnswerError,
    TutorUnavailableError,
)
from lunaris_runtime.persistence import PersistenceError

from ..work_refused import LiveWorkRefusedError

logger = structlog.get_logger()

_UNAVAILABLE = "Live is having trouble reaching its storage. Try again shortly."

#: The tutor being down is a different outage from storage being down, and a learner can tell: one
#: means their session did not open, the other means it may not have been saved. Both end, so both
#: are worth retrying — which is why this is a 503 rather than a session opened with nothing in it.
_TUTOR_UNAVAILABLE = "Live's tutor could not reach its model. Try again shortly."

#: The grader is a different outage from the tutor, and the learner's next step differs: their
#: answer was not scored, so nothing they said has been lost or held against them.
_GRADER_UNAVAILABLE = "Live could not score that answer just now. Try sending it again."

#: A row this build cannot parse never becomes readable by waiting, so it must not read as an
#: outage: "try again" on a permanently unreadable session is an invitation to reload forever.
_UNREADABLE = "This session was saved in a format Live can no longer read."


def translate_failure(exc: Exception, correlated: dict[str, str]) -> HTTPException | None:
    """The HTTP answer to a failure a learner could plausibly act on, or ``None`` to let it fly.

    One place, because every entry point fails in the same ways and drifting apart would mean a
    learner learning what "try again" means from whichever endpoint they hit first. Ordered
    deliberately: ``SessionFormatError`` IS a ``PersistenceError``, and reading as a retryable
    outage is exactly the mistake it exists to prevent.

    Public because P2b's AG-UI stream is the second entry point into these same failures, which is
    exactly the drift this function was written to prevent — the sentence a learner reads must not
    depend on whether their client speaks REST or AG-UI.
    """
    if isinstance(exc, SessionFormatError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_UNREADABLE,
            headers=correlated,
        )
    if isinstance(exc, LiveWorkRefusedError):
        # Every refusal maps the same way, from one place: the throttle and the budget each carry
        # their own status and the sentence a learner reads, so a new one cannot arrive with no
        # words or the wrong code.
        return HTTPException(status_code=exc.status_code, detail=exc.detail, headers=correlated)
    if isinstance(exc, StaleAnswerError):
        # The same 409 family as a closed session, and for the same reason: the request is well
        # formed and the learner did nothing wrong — the question they answered is simply not the
        # one in front of them any more. Re-reading the session is the recovery, not retrying.
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That question has already been answered. Reload to catch up.",
            headers=correlated,
        )
    if isinstance(exc, PlacementNotAnswerableError):
        # T1's honest 409 for an answer to the interview this build cannot read yet; T2 removes it.
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview isn't taking answers yet.",
            headers=correlated,
        )
    if isinstance(exc, SessionClosedError):
        # The request is well formed and the session is real; it is the session's *state* that
        # refuses. A learner with a stale tab should be told it ended, not that they did something
        # wrong and not that it might work on a retry.
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This session has already ended.",
            headers=correlated,
        )
    if isinstance(exc, GraderUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_GRADER_UNAVAILABLE,
            headers=correlated,
        )
    if isinstance(exc, TutorUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_TUTOR_UNAVAILABLE,
            headers=correlated,
        )
    if isinstance(exc, PersistenceError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
            headers=correlated,
        )
    return None


def raise_translated(
    exc: Exception, correlated: dict[str, str], event: str, **fields: object
) -> None:
    """Log a failure with its traceback and re-raise it as the HTTP answer, or let it fly.

    Every entry point into the session plane needs the same four lines — log with a traceback,
    translate, raise the translation, otherwise re-raise — and by the fourth copy the shape had
    started to be the thing being maintained rather than the behaviour. The log event stays a
    parameter because *which* endpoint failed is the one part that genuinely differs.

    The traceback matters: nothing below the router logs one. ``guard`` only translates and the
    stores stay silent, so without this an outage is a bare 500 with no way to tell what broke.
    """
    logger.warning(event, exc_info=True, **fields)
    if (translated := translate_failure(exc, correlated)) is not None:
        raise translated from exc
    raise exc
