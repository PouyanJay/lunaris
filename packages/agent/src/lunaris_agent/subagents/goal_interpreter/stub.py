from lunaris_runtime.schema import CourseBrief


class StubGoalInterpreter:
    """Returns a preconfigured brief. Lets the pipeline be tested without a model."""

    def __init__(self, brief: CourseBrief) -> None:
        self._brief = brief

    async def interpret(self, request: str) -> CourseBrief:
        return self._brief
