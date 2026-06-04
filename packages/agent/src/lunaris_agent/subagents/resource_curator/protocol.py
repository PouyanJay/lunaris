from typing import Protocol

from lunaris_runtime.schema import CourseBrief, Module

from .curation import CuratedResources


class IResourceCurator(Protocol):
    """Finds + vets external learning resources for one module's lesson, bucketed by phase (P7.4).

    Given an authored module (its competency, KCs, objectives, and lesson prose) and the brief, the
    curator searches for candidate resources, scores them for quality + trust + level-match, and
    returns the accepted ``Resource``s assigned to the Merrill phase each supports. Best-effort:
    no source meeting the bar yields empty lists (the lesson keeps its verified content), never an
    exception that aborts the build. Swappable — a live model+search impl vs a deterministic stub.
    """

    async def curate(
        self, module: Module, brief: CourseBrief | None = None
    ) -> CuratedResources: ...
