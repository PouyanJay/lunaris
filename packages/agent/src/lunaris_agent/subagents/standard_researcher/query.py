from lunaris_runtime.schema import CourseBrief, Level


def build_research_queries(brief: CourseBrief) -> list[str]:
    """Two-to-three narrow searches grounding the brief: what the level MEANS + how it's MEASURED.

    When the goal names an external standard the queries target it by name (and, when known, its
    authority body) so research biases toward the source that defines it; otherwise they derive from
    the goal + subject + level. Deterministic — query *planning* needs no model call, only the
    distillation does (cheaper + testable, and the searches stay narrow rather than open-ended).
    """
    standard = brief.target_standard
    if standard is not None:
        queries = [
            f"{standard.name} competency descriptors",
            f"{standard.name} requirements by level",
        ]
        if standard.authority_hint:
            queries.append(f"{standard.name} official requirements {standard.authority_hint}")
        return queries
    level = "" if brief.target_level is Level.NOT_APPLICABLE else f"{brief.target_level.value} "
    return [
        f"{brief.goal} key competencies",
        f"{level}{brief.subject} skills",
    ]
