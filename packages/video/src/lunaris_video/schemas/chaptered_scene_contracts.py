from typing import Self

from pydantic import Field, model_validator

from lunaris_video.schemas._validation import assert_unique_scene_ids
from lunaris_video.schemas.chapter import Chapter
from lunaris_video.schemas.contract_header import ContractHeader
from lunaris_video.schemas.scene_contract import SceneContract


class ChapteredSceneContracts(ContractHeader):
    """The chaptered contract variant — the overview kind's shape (plan §0: 3 chapters of 3-4
    scenes → one MP4).

    Downstream stages (code, render, QA, assemble) iterate scenes regardless of chaptering;
    ``scenes`` flattens in chapter order so they never special-case the shape. Scene ids are
    unique across the WHOLE contract, not per chapter — artifacts share one namespace.
    """

    chapters: list[Chapter] = Field(min_length=1)

    @property
    def scenes(self) -> list[SceneContract]:
        """Every scene in render order — chapters flattened."""
        return [scene for chapter in self.chapters for scene in chapter.scenes]

    @model_validator(mode="after")
    def _scene_ids_must_be_unique_across_chapters(self) -> Self:
        assert_unique_scene_ids(self.scenes, "across chapters — one artifact namespace")
        return self
