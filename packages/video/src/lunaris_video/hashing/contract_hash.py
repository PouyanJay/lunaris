import hashlib
import json

from lunaris_video.schemas import VideoContract


def contract_hash(contract: VideoContract) -> str:
    """SHA-256 over the contract's canonical JSON — the regeneration cache key (principle 5).

    The contract is regeneration-stable by design (skill spec): re-running Stage 2+ on an
    unchanged contract produces an equivalent video, so the pipeline may skip render work when
    this hash matches existing artifacts. Canonical = sorted keys + compact separators, making
    the digest independent of construction order and serializer whitespace.
    """
    canonical = json.dumps(
        contract.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
