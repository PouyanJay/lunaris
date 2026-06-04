"""A deterministic, key-free goal interpreter: a topic-derived default brief (P7.5).

Used by the brief endpoint when no model key is reachable, so the interpret clarifier still renders
with sensible defaults the learner can fill in. Distinct from :class:`StubGoalInterpreter` (which
returns a fixed brief supplied for tests): this derives the subject/goal from the request and leaves
level/preferences at their defaults — an honest "we didn't infer; tell us" starting point.
"""

from lunaris_runtime.schema import CourseBrief


class DefaultGoalInterpreter:
    """Build a default :class:`CourseBrief` from the raw request, with no model inference."""

    async def interpret(self, request: str) -> CourseBrief:
        topic = request.strip()
        return CourseBrief(subject=topic, goal=topic)
