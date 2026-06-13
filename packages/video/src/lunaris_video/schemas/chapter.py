from pydantic import Field

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.scene_contract import SceneContract


class Chapter(ContractModel):
    """One chapter of a chaptered contract — a titled run of scenes inside one video.

    Chapters exist because a ~3 minute overview exceeds the skill's validated 3-to-5-scene
    envelope (plan §0): each chapter stays inside the envelope, and the chapters concatenate
    into one MP4.
    """

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scenes: list[SceneContract] = Field(min_length=1)
