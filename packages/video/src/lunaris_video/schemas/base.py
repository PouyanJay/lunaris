from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for every scene-contract schema (the persisted ``scene_contracts.json``).

    The wire format here is the pinned skill's contract spec (``references/contract-schema.md``)
    — snake_case JSON, exactly as the planner writes it and the gates audit it. This is why it
    does NOT extend the web-facing ``CourseModel`` (camelCase aliases): the contract's consumer
    is the pipeline and the skill spec, not the TypeScript client. ``extra="forbid"`` makes a
    hallucinated field a loud validation error instead of silently persisted noise.
    """

    model_config = ConfigDict(extra="forbid")
