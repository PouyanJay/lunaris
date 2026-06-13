from typing import Self

from pydantic import Field, model_validator

from lunaris_video.schemas.base import ContractModel

# Two schemas in one file by the tightly-coupled-sibling exception: QaVerdict holds list[QaDefect]
# and the two are never used apart.


class QaDefect(ContractModel):
    """One spatial/visual defect the vision gate found in a scene's frames.

    ``issue`` names what is wrong (against the skill's QA checklist — clipping, overlap,
    off-pivot rotation, label drift, container overflow); ``fix_hint`` is the targeted edit the
    repair turn should make. Both feed the visual-repair prompt verbatim.
    """

    issue: str = Field(min_length=1)
    fix_hint: str = Field(min_length=1)


class QaVerdict(ContractModel):
    """Gate B's verdict on one scene: clean, or a list of defects to repair.

    ``passed`` and ``defects`` are kept consistent by construction — a passing verdict has no
    defects, and a defect list cannot be marked passed — so a malformed vision completion that
    says "passed with 3 defects" is a parse failure (a repair turn), never a silently shipped
    broken scene.
    """

    passed: bool
    defects: list[QaDefect] = Field(default_factory=list)

    @model_validator(mode="after")
    def _passed_iff_no_defects(self) -> Self:
        if self.passed and self.defects:
            raise ValueError("a passing verdict cannot carry defects")
        if not self.passed and not self.defects:
            raise ValueError("a failing verdict must name at least one defect")
        return self
