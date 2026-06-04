from dataclasses import dataclass

from lunaris_runtime.schema import AuthorityKind, SourceType, SubjectField, TrustTier


@dataclass(frozen=True)
class SourceAuthority:
    """One row of the editable ``source_authorities`` config (P6.2): a domain and its trust prior.

    The authority table is a *prior, not a gate* (plan §4a): a ``SPINE`` domain is authoritative
    across every topic, a ``PACK`` domain only for runs in its ``field``, a ``DENYLIST`` domain is
    never ingested. ``trust_tier`` is the prior the credibility scorer reads; ``source_type`` is an
    optional default kind for the domain (e.g. a database vs docs). Domain entities flow inside
    Python as frozen dataclasses; the contract for managing them is a Pydantic schema in the API.
    """

    domain: str
    kind: AuthorityKind
    trust_tier: TrustTier
    field: SubjectField | None = None
    source_type: SourceType | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        # A pack is field-scoped by definition; spine/denylist are global. Catch a mis-entered row
        # here rather than letting a field-less pack silently never match (or a fielded spine match
        # too narrowly) deep in the scorer's lookup.
        if self.kind is AuthorityKind.PACK and self.field is None:
            raise ValueError("a PACK authority must name a field")
        if self.kind is not AuthorityKind.PACK and self.field is not None:
            raise ValueError(f"a {self.kind} authority must not name a field")
