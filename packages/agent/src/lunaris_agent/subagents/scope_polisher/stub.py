from lunaris_runtime.schema import CourseBrief, CourseScope


class StubScopePolisher:
    """Returns the deterministic band unchanged — the identity polish.

    The honest no-key outcome the composition root wires when no Anthropic key is set (and the
    default in tests): the scope band is exactly what the estimator produced, byte for byte, so the
    keyless path is deterministic.
    """

    async def polish(self, scope: CourseScope, *, brief: CourseBrief | None) -> CourseScope:
        return scope
