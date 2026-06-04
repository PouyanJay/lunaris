from typing import Protocol

from lunaris_grounding.evidence import Evidence


class IEvidenceRetriever(Protocol):
    """Retrieves evidence for a claim from the grounding corpus.

    The MVP corpus backend is Supabase pgvector + an embeddings provider (D2); until
    those creds exist a stub is used. Implementations are swappable behind this Protocol.
    ``course_id`` scopes retrieval to one course's chunks (P6.1) — the verifier passes the course
    being built so a claim only grounds against that course's own (vouched) evidence, never another
    topic's; ``None`` searches the whole corpus (the legacy path).
    """

    async def retrieve(
        self, claim_text: str, *, course_id: str | None = None
    ) -> list[Evidence]: ...
