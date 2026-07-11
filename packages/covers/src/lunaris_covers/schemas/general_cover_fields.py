from pydantic import BaseModel, ConfigDict, Field


class GeneralCoverFields(BaseModel):
    """The variables Claude fills in the GENERAL cover-prompt template — nothing more.

    The operator's course-cover prompt system (general-preset template fidelity) is explicit about
    the division of labor: the LLM generates ONLY the descriptive fields; the full structured
    prompt is assembled deterministically and sent to the image model verbatim. This schema is that
    contract — a pipeline-internal parse target (snake_case ``BaseModel``, like ``CoverQaVerdict``),
    parsed with bounded repair turns so a malformed completion never fails a cover outright.
    """

    model_config = ConfigDict(extra="forbid")

    subtitle: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    primary_visual: str = Field(min_length=1)
    supporting_visuals: str = Field(min_length=1)
    process_visualization: str = Field(min_length=1)
