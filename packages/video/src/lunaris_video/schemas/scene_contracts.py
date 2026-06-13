from typing import Self

from pydantic import Field, model_validator

from lunaris_video.schemas._validation import assert_unique_scene_ids
from lunaris_video.schemas.contract_header import ContractHeader
from lunaris_video.schemas.scene_contract import SceneContract


class SceneContracts(ContractHeader):
    """The flat contract file — the validated shape of ``scene_contracts.json`` for a lesson.

    This is the pipeline's central artifact: the planner writes it, codegen implements it, the
    gates audit against it, and the contract hash over it is the regeneration cache key. The
    skill's validated envelope is 3-5 scenes of 15-30s; that is planner guidance enforced by
    the PLAN prompt, not the schema — the schema enforces what would corrupt the pipeline
    (empty contract, colliding scene ids).
    """

    scenes: list[SceneContract] = Field(min_length=1)

    @model_validator(mode="after")
    def _scene_ids_must_be_unique(self) -> Self:
        assert_unique_scene_ids(self.scenes, "— artifacts and Scene classes key off them")
        return self
