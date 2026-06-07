from collections.abc import Callable

from lunaris_runtime.schema import CourseBrief, Modality, Module

from .curation import CuratedResources


class StubResourceCurator:
    """Returns curated resources from a configurable function of the module (no search, no model).

    Lets the curation → finalize pipeline be tested without a search backend or a model. The default
    function yields empty resources — the honest no-key degradation (the composition root selects
    this stub when no ``SEARCH_API_KEY`` is set, so CI curates deterministically to nothing).
    ``modality`` is accepted for protocol parity (CQ Phase 2) and ignored — the stub does no search.
    """

    def __init__(self, fn: Callable[[Module], CuratedResources] | None = None) -> None:
        self._fn = fn or (lambda _module: CuratedResources())

    async def curate(
        self,
        module: Module,
        brief: CourseBrief | None = None,
        *,
        modality: Modality | None = None,
    ) -> CuratedResources:
        return self._fn(module)
