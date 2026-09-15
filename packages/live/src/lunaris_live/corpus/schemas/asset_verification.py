from pydantic import Field

from .base import CorpusModel


class AssetVerification(CorpusModel):
    run_id: str = Field(min_length=1, max_length=100)
    verifier_version: str = Field(min_length=1, max_length=100)
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
