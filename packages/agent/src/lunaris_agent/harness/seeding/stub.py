"""The no-op seeder — the no-key / offline default."""

from ..draft import CourseDraft
from .report import SeedReport


class StubGroundingSeeder:
    """Ingests nothing and reports an empty pass (the no-corpus-credentials default).

    Lets the agent pipeline run end-to-end offline: the ``seed_grounding`` tool still lights the
    Grounding phase, but no source is ingested, so claims fall to the verifier's existing behaviour
    (CUT against an empty corpus → REVIEW). The live :class:`GroundingSeeder` replaces it when the
    embeddings + corpus credentials are present.
    """

    async def seed(self, draft: CourseDraft) -> SeedReport:
        return SeedReport()
