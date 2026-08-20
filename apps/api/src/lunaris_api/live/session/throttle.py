from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from ...daily_counter import DailyCounter
from ...local_owner_key import LOCAL_OWNER_KEY
from ..work_refused import LiveWorkRefusedError


class LiveSessionDailyCapReachedError(LiveWorkRefusedError):
    """The owner has opened their allowance of sessions today."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.detail = (
            f"You've opened today's {cap} sessions. They reset tomorrow — the maps you already "
            "have stay where they are."
        )
        super().__init__(self.detail)


class LiveSessionBusyError(LiveWorkRefusedError):
    """A turn is already being taken in this session, so a second would pay for the same one twice.

    Not a theoretical race. A double-click, a client retry, or a script sends two answers naming the
    same turn; both load the same session, both pass every check made against that snapshot, and
    both call a grader and a tutor before either tries to write. The write is settled afterwards by
    the store's compare-and-set — but by then the money is spent, and the per-session ceiling cannot
    see spend that has not been drained yet. The only place to stop it is before the billed calls.
    """

    status_code = 409
    detail = (
        "Your last answer is still being marked. Give it a moment rather than sending it again."
    )


class LiveSessionBudgetExhaustedError(LiveWorkRefusedError):
    """This session has spent its ceiling, so it takes no further turns.

    A runaway guard rather than a ration: a session is bounded by its clock already, and this only
    binds when something is wrong — a loop of retries, or a learner (or a script) answering far past
    the point where the sitting was a sitting.
    """

    def __init__(self, spent_usd: float, budget_usd: float) -> None:
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd
        self.detail = (
            "This session has reached its cost ceiling, so it has stopped here. What you "
            "demonstrated is saved — starting a fresh session picks up from it."
        )
        super().__init__(self.detail)


class LiveSessionStillOpenError(LiveWorkRefusedError):
    """A topic cannot be forgotten while a session on it is still going (T5).

    Not a throttle and not a race lost: a session in progress holds the learner model in memory and
    writes it back at the end of every turn, so clearing the beliefs underneath one would be undone
    by the next turn, silently. Refusing is the only answer that stays true a second later, and the
    detail says what to do about it rather than only that it did not happen.
    """

    status_code = 409

    def __init__(self, graph_id: str) -> None:
        self.graph_id = graph_id
        self.detail = (
            "You still have a session going on this topic. Finish it or leave it first, then "
            "clearing what Lunaris knows about you here will stick."
        )
        super().__init__(self.detail)


class LiveSessionThrottle:
    """Admission control for the session plane.

    Only the *opening* is counted. A turn is not rationed by number, because a session is already
    bounded by its clock and by its own cost ceiling — capping turns as well would end sittings that
    were going well for a reason nobody could explain to the learner. Opening is where a runaway
    starts: a script that opens sessions in a loop pays a tutor call each time.

    In-process, like the compile plane's: the counters live in memory, reset on restart and do not
    coordinate across replicas — sufficient for a single-replica deploy, with a DB-backed ledger as
    the documented upgrade path.
    """

    def __init__(self, *, open_daily_cap: int, clock: Callable[[], datetime] | None = None) -> None:
        self._open_daily_cap = open_daily_cap
        self._opens = DailyCounter(clock=clock) if clock else DailyCounter()
        # Which sessions have a turn in flight. A set rather than a count: a session takes one turn
        # at a time by definition — the learner is answering the question in front of them.
        self._in_flight: set[str] = set()

    def admit_open(self, owner_id: str | None) -> None:
        """Count one session opening against today's allowance, or refuse it.

        Raises ``LiveSessionDailyCapReachedError`` when the owner has used the allowance. A cap of
        0 or less leaves openings unrationed, which is what the suites that predate this compose.
        """
        if self._open_daily_cap <= 0:
            return
        # Checked before counting, so a refused opening does not spend the allowance it was refused
        # by — otherwise a learner who hit the cap could never get back under it.
        self.check_open(owner_id)
        self._opens.count(_key(owner_id))

    def check_open(self, owner_id: str | None) -> None:
        """Refuse an opening the allowance would not admit, without counting one (P2c T8).

        For an opening that has a second gate to pass before it exists (a topic-open's compile,
        admitted by the compile plane): checked here first, so a refusal from either gate spends
        nothing, and counted with ``admit_open`` once both have said yes. Synchronous, like the
        rest of the throttle, so nothing can slip between the check and the count.
        """
        if self._open_daily_cap <= 0:
            return
        if self._opens.used(_key(owner_id)) >= self._open_daily_cap:
            raise LiveSessionDailyCapReachedError(self._open_daily_cap)

    def is_taking_turn(self, session_id: str) -> bool:
        """Whether a turn is in flight for this session right now.

        Asked by ``forget``, which cannot claim the slot itself because it is keyed by session and
        a reset is keyed by map. A turn holds its slot across **both** of its writes, so this is
        what closes the window between them (see ``LiveSessionService.forget``).
        """
        return session_id in self._in_flight

    @contextmanager
    def taking_turn(self, session_id: str) -> Iterator[None]:
        """Hold this session's single turn slot for the length of a turn.

        Claimed *before* the grader and the tutor are called, so a duplicate submission is refused
        while it is still free — the compare-and-set on the write settles which answer counts, but
        it settles it after both have been paid for. Released in a ``finally`` so a failed turn does
        not lock a learner out of their own session.

        Safe without a lock: claiming and releasing are synchronous, and the event loop cannot
        interleave two of them.
        """
        if session_id in self._in_flight:
            raise LiveSessionBusyError
        self._in_flight.add(session_id)
        try:
            yield
        finally:
            self._in_flight.discard(session_id)


def _key(owner_id: str | None) -> str:
    """Who the allowance belongs to. An unowned request is the single-user path, which is one
    learner however many tabs they have — so they share one bucket rather than getting none. The
    same constant every other throttle in this API uses for that caller."""
    return owner_id or LOCAL_OWNER_KEY
