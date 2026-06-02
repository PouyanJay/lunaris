from .base import CourseModel
from .enums import RunEventKind


class RunEvent(CourseModel):
    """One persisted row of a run's streamed build log — the unit of timeline *replay*.

    Where ``CourseRun`` is the one-row-per-build index, this is the append-only transcript: every
    coarse ``progress`` stage and fine-grained ``agent`` beat the live SSE emitted, captured in
    emission order so a finished (or still-building) run can be re-rendered into the same
    ``BuildTimeline``. ``seq`` is the run-scoped monotonic emission index (assigned where the two
    streams interleave, so order survives without wall-clock), and ``payload`` is the original
    event's camelCase wire dict (``ProgressEvent`` or ``AgentEvent``, per ``kind``) — stored as-is
    so replay consumes exactly what the live stream did. The DB owns a ``created_at`` for ops; it is
    not part of the replay contract (``seq`` is the order), so it is not surfaced here.
    """

    run_id: str
    course_id: str
    seq: int
    kind: RunEventKind
    payload: dict[str, object]
