from enum import StrEnum


class PacketKind(StrEnum):
    """Which course unit a grounding packet grounds.

    ``LESSON`` packets are built in V2; ``SUMMARY`` (course trailer) and ``OVERVIEW`` (topic intro)
    are defined now so the packet shape is stable, and their builders are wired in V5 with the
    course-level videos phase.
    """

    LESSON = "lesson"
    SUMMARY = "summary"
    OVERVIEW = "overview"
