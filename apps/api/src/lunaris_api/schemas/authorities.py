from typing import Self

from lunaris_grounding import SourceAuthority
from lunaris_runtime.schema import AuthorityKind, SourceType, SubjectField, TrustTier
from pydantic import Field, model_validator

from .base import CamelModel


class SourceAuthorityRequest(CamelModel):
    """Request body for adding/replacing a row in the trust-config (P6.2 §4a).

    A row's identity is ``(domain, field)``, so re-submitting the same pair edits it (upsert). The
    pack-has-field invariant is enforced at the boundary (→ 422) so a malformed row never reaches
    the store's domain model (which raises on the same rule).
    """

    domain: str = Field(min_length=1, max_length=253)
    kind: AuthorityKind
    tier: TrustTier
    field: SubjectField | None = None
    source_type: SourceType | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _pack_has_field(self) -> Self:
        if self.kind is AuthorityKind.PACK and self.field is None:
            raise ValueError("a pack authority must name a field")
        if self.kind is not AuthorityKind.PACK and self.field is not None:
            raise ValueError(f"a {self.kind.value} authority must not name a field")
        return self

    def to_model(self) -> SourceAuthority:
        return SourceAuthority(
            domain=self.domain.strip().lower(),
            kind=self.kind,
            trust_tier=self.tier,
            field=self.field,
            source_type=self.source_type,
            note=self.note,
        )


class SourceAuthorityView(CamelModel):
    """One trust-config row on the wire (camelCase). Enum fields keep their type (StrEnum)."""

    domain: str
    kind: AuthorityKind
    tier: TrustTier
    field: SubjectField | None = None
    source_type: SourceType | None = None
    note: str | None = None

    @classmethod
    def of(cls, authority: SourceAuthority) -> "SourceAuthorityView":
        return cls(
            domain=authority.domain,
            kind=authority.kind,
            tier=authority.trust_tier,
            field=authority.field,
            source_type=authority.source_type,
            note=authority.note,
        )
