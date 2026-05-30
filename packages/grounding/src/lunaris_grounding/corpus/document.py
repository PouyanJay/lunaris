from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingDocument:
    """A single embedded corpus chunk: the text, its vector, and source provenance.

    ``id`` is deterministic (a hash of kc + content) so re-ingesting the same source is
    idempotent. ``embedding`` is stored as a tuple to keep the entity immutable.
    """

    id: str
    kc_id: str
    content: str
    embedding: tuple[float, ...]
    title: str | None = None
    url: str | None = None
    run_id: str | None = None
