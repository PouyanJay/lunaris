from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateSource:
    """A candidate grounding source for a KC, before chunking/embedding.

    D3 (MVP): general/open retrieval feeds these in; ingestion chunks ``text``, embeds it,
    and writes the chunks to the corpus keyed by ``kc_id``.
    """

    kc_id: str
    text: str
    title: str | None = None
    url: str | None = None
