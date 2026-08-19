import structlog

from .protocols import ITutorDeltaSink

logger = structlog.get_logger()


def relay_delta(sink: ITutorDeltaSink | None, delta: str) -> None:
    """Pass one fragment of the tutor's words on, if anyone is listening, without ever costing the
    turn.

    The counterpart of the graph plane's ``report_progress``, and it exists for the same reason: a
    sink is a client's connection by another name, and clients disappear mid-turn — a learner closes
    the tab, a proxy times the stream out. Letting that propagate would trade a paid-for turn for a
    lost animation, and the turn is the thing with a grader call and a tutor call behind it.

    Internal to the session package: the loop relays, nothing else does.
    """
    if sink is None:
        return
    try:
        sink(delta)
    except Exception:
        # Debug, not warning: a disconnected learner is ordinary, and a turn of forty fragments
        # would otherwise log forty warnings for one closed tab.
        logger.debug("live.session.delta_sink_failed", exc_info=True)
