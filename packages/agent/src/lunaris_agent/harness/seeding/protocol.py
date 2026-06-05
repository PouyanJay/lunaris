from typing import Protocol

from ..draft import CourseDraft
from .report import SeedReport


class IGroundingSeeder(Protocol):
    """Seeds the per-course corpus from the pages the research stage already fetched (P6.4).

    Called by the ``seed_grounding`` tool after the curriculum is designed and before discovery, so
    the corpus is filled first from evidence the build already paid for, then discovery only has to
    cover the gaps. The real implementation turns ``draft.research_seeds`` into corpus sources and
    ingests them through the SAME credibility scorer + trust floor as every other acquisition mode
    (seeded is not the same as trusted); the stub ingests nothing, so the no-key path stays
    deterministic and the corpus stays empty (claims fall to the verifier's existing behaviour).

    Reads the run's research seeds and writes graded, provenanced ``SEED`` sources to the corpus via
    the draft; returns a :class:`SeedReport` summarizing what landed. Best-effort: seeding never
    aborts a build — a failure leaves the corpus as-is and the verifier cuts the unsupported claims.
    """

    async def seed(self, draft: CourseDraft) -> SeedReport: ...
