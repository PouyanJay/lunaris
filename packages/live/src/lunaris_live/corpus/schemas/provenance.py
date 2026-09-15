from typing import Literal

from pydantic import Field

from .reference import CorpusReference


class CorpusProvenance(CorpusReference):
    title: str = Field(min_length=1, max_length=500)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    adapter_version: str = Field(default="studio-v1", min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=100)
    status: Literal["pending", "verified", "failed"] = "pending"
