from typing import Protocol

from ..draft import CourseDraft
from .report import DiscoveryReport


class IGroundingDiscoverer(Protocol):
    """Discovers, vets, and ingests evidence for a course's concepts (the P6.3 discovery stage).

    Called by the ``discover_grounding`` tool after the curriculum is designed and before authoring,
    so the per-course corpus exists when claims are verified. The real implementation runs a bounded
    LangGraph sub-graph (plan → search → fetch → score → ingest → reflect) that emits its steps live
    onto the run's agent channel; the stub ingests nothing, so the no-key path stays deterministic.

    Reads the run's concepts/brief and writes graded, provenanced sources to the corpus via the
    draft; returns a :class:`DiscoveryReport` summarizing what landed. Best-effort: discovery never
    aborts a build — a failure leaves the corpus as-is and the verifier cuts the unsupported claims.
    """

    async def discover(self, draft: CourseDraft) -> DiscoveryReport: ...
