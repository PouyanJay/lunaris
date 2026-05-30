import structlog
from lunaris_runtime.schema import Course, MayerFlags, Visual, VisualKind

from .protocol import IVisualGenerator
from .renderer_protocol import IDiagramRenderer

logger = structlog.get_logger()


class VisualEngine:
    """Deterministic visual placement (build-spec §07, Stage 5).

    For each lesson's demonstrate segment (where the core teaching lives), it asks the
    generator for a diagram, renders + validates it in the sandbox, and attaches a ``Visual``
    only when it renders cleanly — regenerating up to ``max_repairs`` times on failure. A
    diagram that still won't render is skipped: no broken or decorative visual ever ships.
    """

    def __init__(
        self,
        generator: IVisualGenerator,
        renderer: IDiagramRenderer,
        *,
        max_repairs: int = 1,
    ) -> None:
        self._generator = generator
        self._renderer = renderer
        self._max_repairs = max_repairs

    async def illustrate(self, course: Course) -> int:
        """Attach validated visuals across the course; returns how many were placed.

        Mutates the course in place (consistent with the rest of the orchestrator, which
        fills the single course-object slice by slice); the count is returned for logging.
        """
        placed = 0
        for module in course.modules:
            for lesson in module.lessons:
                visual = await self._make_visual(module.title, lesson.segments.demonstrate.prose)
                if visual is not None:
                    lesson.segments.demonstrate.visuals.append(visual)
                    placed += 1
        logger.info("visuals_placed", count=placed)
        return placed

    async def _make_visual(self, concept: str, context: str) -> Visual | None:
        draft = await self._generator.generate(concept, context)
        if draft is None:
            return None  # the generator judged no diagram helps (coherence) — not a repair case

        for attempt in range(self._max_repairs + 1):
            result = await self._renderer.render(draft.source)
            if result.ok:
                logger.info("visual_placed", concept=concept)
                return Visual(
                    kind=VisualKind.MERMAID,
                    source=draft.source,
                    rendered=result.path,
                    # coherence is the generator's decision to draw at all; signaling is a
                    # property of the diagram we don't verify here — leave it at its default.
                    mayer_checks=MayerFlags(coherence=True),
                )
            if attempt == self._max_repairs:
                break
            # Repair: feed the render error back so the generator can produce a fixed diagram.
            repair_context = (
                f"{context}\n\n[The previous diagram failed to render: {result.error}. "
                "Produce a simpler, valid diagram.]"
            )
            draft = await self._generator.generate(concept, repair_context)
            if draft is None:
                return None

        logger.warning("visual_skipped_unrenderable", concept=concept)
        return None
