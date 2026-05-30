from collections.abc import Callable

from lunaris_agent import Orchestrator
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course

OrchestratorFactory = Callable[[CourseStore], Orchestrator]


class CourseService:
    """Application service over the course pipeline — the API's only door to the agent.

    Builds an orchestrator per run via the injected factory (live or stub) and persists
    through the shared ``CourseStore``, so the HTTP layer stays free of pipeline wiring.
    """

    def __init__(self, store: CourseStore, orchestrator_factory: OrchestratorFactory) -> None:
        self._store = store
        self._factory = orchestrator_factory

    async def create(self, topic: str, *, course_id: str, run_id: str) -> Course:
        orchestrator = self._factory(self._store)
        return await orchestrator.run(topic, course_id=course_id, run_id=run_id)

    def get(self, course_id: str) -> Course | None:
        try:
            return self._store.load(course_id)
        except FileNotFoundError:
            return None
