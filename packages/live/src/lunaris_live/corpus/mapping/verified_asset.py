import hashlib
import json

from ..schemas.asset import NodeAsset
from ..schemas.asset_verification import AssetVerification
from .models.candidate import MappingCandidate
from .models.request import MappingRequest
from .schemas.report import MappingDecision


def verified_asset(
    request: MappingRequest, candidate: MappingCandidate, decision: MappingDecision
) -> NodeAsset:
    """Copy authenticated source bytes, never a model-provided rewritten excerpt."""
    identity = json.dumps(
        [request.snapshot.source.digest, decision.node_id, candidate.locator], separators=(",", ":")
    )
    return NodeAsset(
        asset_id=hashlib.sha256(identity.encode()).hexdigest(),
        kind=candidate.kind,
        origin="ingested",
        locator=candidate.locator,
        source_digest=request.snapshot.source.digest,
        title=candidate.title[:500],
        excerpt=candidate.excerpt,
        source_label=request.snapshot.source.title[:500],
        clip=candidate.clip,
        verification=AssetVerification(
            run_id=request.run_id,
            verifier_version="mapping-verifier-v1",
            source_digest=request.snapshot.source.digest,
        ),
    )
