from dataclasses import dataclass


@dataclass(frozen=True)
class LearnerProfile:
    """The learner profiler's output: the frontier of concepts the learner already knows.

    The frontier is the ZPD lower bound — the foundations a learner at the brief's level can be
    assumed to have, which the course must therefore NOT re-teach. Empty for a true novice (teach
    from the foundations). Entries are concept descriptors, not KC ids.
    """

    frontier: list[str]
