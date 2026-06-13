from pydantic import Field

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.beat import Beat


class SceneContract(ContractModel):
    """One scene's contract: what must exist on screen, beat by beat, and what it may claim.

    ``id`` follows the spec pattern ``S<N>_<slug>`` — files, logs, QA frames, per-scene MP4s and
    the generated Manim class all key off it. ``sources`` is schema-enforced non-empty: a scene
    with numbers and no sources is itself a gate failure (contract-schema field rules); scenes
    making no empirical claims carry the spec's literal framing-only sentinel. ``duration_s`` is
    a target only — actual timing comes from ``timing.json`` once narration is resolved.
    """

    id: str = Field(pattern=r"^S\d+_[a-z0-9_]+$")
    archetype: str = Field(min_length=1)
    narration: str
    objects: list[str] = Field(min_length=1)
    beats: list[Beat] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    duration_s: float = Field(gt=0)

    @property
    def scene_class_name(self) -> str:
        """The name codegen MUST give this scene's class — the render runner selects scenes by
        class name on the manim CLI, so any drift between this and the generated source means
        the scene silently never renders."""
        head, *words = self.id.split("_")
        return head + "".join(word.capitalize() for word in words)
