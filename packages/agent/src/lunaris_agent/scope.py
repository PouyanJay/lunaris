"""The scope-realism estimator (CQ Phase 3.1): an honest at-a-glance framing of a course.

Computes a ``CourseScope`` — effort/timeline + what the course does and does not get you — from the
brief's abstractions (goal_type, gap magnitude, target level, grounding status), never from a topic,
so the framing is generic across any subject (the Genericity Rule). Pure + deterministic; the
finalize tool applies it, and an optional key-gated polish step may refine its wording without
changing its facts. T0 is a trivial walking-skeleton band; T1 fills in the real estimation.
"""

from lunaris_runtime.schema import Course, CourseBrief, CourseScope


def estimate_scope(course: Course, brief: CourseBrief | None) -> CourseScope:
    """The scope-realism band for a finalized course. Deterministic; topic-blind.

    Reads the brief's abstractions (not the topic). With no brief (the stub/legacy direct-assembly
    path) it falls back to the course's own ``goal_type``. T0 returns a populated placeholder band
    proving the finalize→persist→wire path; T1 replaces the body with real effort/scope logic.
    """
    goal_type = brief.goal_type if brief else course.goal_type
    return CourseScope(
        effort="A few weeks · self-paced",
        delivers=[f"A grounded {goal_type.value} course built backward from your goal."],
        excludes=["Anything beyond the scope of the modules below."],
    )
