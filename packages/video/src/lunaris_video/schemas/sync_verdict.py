from typing import Self

from pydantic import model_validator

from lunaris_video.schemas.base import ContractModel


class SyncVerdict(ContractModel):
    """Gate D's verdict on one beat's midpoint frame: does it show what the narration describes?

    ``matches`` is the answer; ``reason`` explains a mismatch (a failing verdict must justify itself
    so the failure record names what the gate saw, not just that it fired — a passing verdict needs
    no reason). A malformed completion that says "no match" with no reason is a parse failure (a
    repair turn), never a silently-shipped desync.
    """

    matches: bool
    reason: str = ""

    @model_validator(mode="after")
    def _a_mismatch_must_explain(self) -> Self:
        if not self.matches and not self.reason.strip():
            raise ValueError("a non-matching verdict must give a reason")
        return self
