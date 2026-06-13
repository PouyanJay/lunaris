from dataclasses import dataclass


@dataclass(frozen=True)
class LessonSource:
    """What the PLAN node knows about a lesson — the pipeline-internal view of its inputs.

    Deliberately minimal and decoupled from the course payload's shape: the composition layer
    maps a real ``Lesson`` (module title, Merrill segment prose, learner audience) into this,
    so the planner never reaches into course internals. V2 extends the picture with the
    grounding packet; V1 plans from the verified lesson text alone.
    """

    course_topic: str
    lesson_title: str
    audience: str
    prose: str

    def __post_init__(self) -> None:
        # A blank field here would surface later as a model hallucination (an empty lesson block
        # in the prompt), so construction is where it fails.
        for name in ("course_topic", "lesson_title", "audience", "prose"):
            if not getattr(self, name).strip():
                raise ValueError(f"LessonSource.{name} must not be blank")
