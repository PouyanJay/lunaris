from dataclasses import dataclass

from lunaris_video.models.grounded_claim import GroundedClaim
from lunaris_video.models.packet_kind import PacketKind


@dataclass(frozen=True)
class GroundingPacket:
    """The grounding a video plans against: the verifier-PASSED claims for one course unit.

    Grounding flows from the moat, never re-derived (cross-cutting principle 2) — every claim
    here cleared the verifier, and nothing else may reach a scene. An empty packet is valid: it
    means the unit has no supported empirical claims, so the video must be framing-only.
    """

    kind: PacketKind
    claims: tuple[GroundedClaim, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.claims

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(claim.id for claim in self.claims)

    def by_id(self, claim_id: str) -> GroundedClaim | None:
        return next((claim for claim in self.claims if claim.id == claim_id), None)
