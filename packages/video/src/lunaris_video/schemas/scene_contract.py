from typing import Self

from pydantic import Field, model_validator

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.beat import Beat

FRAMING_ONLY_SENTINEL = "framing only - no empirical claims"
"""The literal a scene carries in ``sources`` when it asserts no empirical facts — the only
permitted alternative to a list of grounding-claim ids (V2 grounding contract)."""


class SceneContract(ContractModel):
    """One scene's contract: what must exist on screen, beat by beat, and what it may claim.

    ``id`` follows the spec pattern ``S<N>_<slug>`` — files, logs, QA frames, per-scene MP4s and
    the generated Manim class all key off it. ``sources`` is schema-enforced non-empty and is
    either the grounding-claim ids the scene draws facts from (V2) or, for a scene that asserts
    nothing, the literal ``FRAMING_ONLY_SENTINEL`` standing alone — never a mix of the two.
    ``duration_s`` is a target only — actual timing comes from ``timing.json`` once narration is
    resolved.
    """

    id: str = Field(pattern=r"^S\d+_[a-z0-9_]+$")
    archetype: str = Field(min_length=1)
    narration: str
    objects: list[str] = Field(min_length=1)
    beats: list[Beat] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    duration_s: float = Field(gt=0)
    # A short, human chapter title for the Cinema video-led reader (phase-5). Optional and
    # back-compatible: courses built before the planner emitted it have none, and the reader
    # derives a label from the scene id instead.
    title: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _sources_are_claim_ids_or_framing_only(self) -> Self:
        # "framing only" means the scene asserts NO facts. Mixing the sentinel with a claim id
        # contradicts that — sources is either [sentinel] alone or a list of claim ids, never both.
        if FRAMING_ONLY_SENTINEL in self.sources and self.sources != [FRAMING_ONLY_SENTINEL]:
            raise ValueError(
                "sources is either the framing-only sentinel alone or a list of claim ids, not both"
            )
        return self

    @property
    def scene_class_name(self) -> str:
        """The name codegen MUST give this scene's class — the render runner selects scenes by
        class name on the manim CLI, so any drift between this and the generated source means
        the scene silently never renders."""
        head, *words = self.id.split("_")
        return head + "".join(word.capitalize() for word in words)
