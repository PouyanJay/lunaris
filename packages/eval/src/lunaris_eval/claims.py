from lunaris_runtime.schema import Claim, Course


def collect_claims(course: Course) -> list[Claim]:
    """Every factual claim across the course's lessons (all four Merrill phases)."""
    claims: list[Claim] = []
    for module in course.modules:
        for lesson in module.lessons:
            segments = lesson.segments
            for phase in (
                segments.activate,
                segments.demonstrate,
                segments.apply,
                segments.integrate,
            ):
                claims.extend(phase.claims)
    return claims
