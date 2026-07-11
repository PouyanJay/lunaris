from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Two schemas in one file by the tightly-coupled-sibling exception: CoverQaVerdict holds
# list[CoverQaDefect] and the two are never used apart. This is a pipeline contract (the vision
# model's parsed JSON), not a persisted course object — so it uses a plain snake_case BaseModel,
# not the camelCase CourseModel the web consumes.


class CoverQaDefect(BaseModel):
    """One anti-slop defect the vision gate found in a rendered cover.

    ``issue`` names what is wrong against the house-style rubric (text in the image, a
    busy/cluttered composition, an off-brand palette, a photoreal/3D finish, a subject that ignores
    the topic). Fed verbatim into the next art-direction round so the regenerate fixes what failed.
    """

    model_config = ConfigDict(extra="forbid")

    issue: str = Field(min_length=1)


class CoverQaVerdict(BaseModel):
    """The vision gate's verdict on a rendered cover: on-brand, or a list of defects to regenerate.

    ``passed`` and ``defects`` are kept consistent by construction — a passing verdict has no
    defects, and a failing verdict must name at least one — so a malformed completion that says
    "passed with defects" is a parse failure (a repair turn), never a silently shipped slop cover.
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    defects: list[CoverQaDefect] = Field(default_factory=list)

    @model_validator(mode="after")
    def _passed_iff_no_defects(self) -> Self:
        if self.passed and self.defects:
            raise ValueError("a passing verdict cannot carry defects")
        if not self.passed and not self.defects:
            raise ValueError("a failing verdict must name at least one defect")
        return self
