from typing import Protocol

from lunaris_grounding.evidence import Evidence


class IEvidenceRetriever(Protocol):
    """Retrieves evidence for a claim from the grounding corpus.

    The MVP corpus backend is Supabase pgvector + an embeddings provider (D2); until
    those creds exist a stub is used. Implementations are swappable behind this Protocol.
    """

    async def retrieve(self, claim_text: str) -> list[Evidence]: ...
