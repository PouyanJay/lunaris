from dataclasses import dataclass

from lunaris_runtime.schema import CoverStylePreset


@dataclass(frozen=True)
class CoverBrief:
    """What the art director needs to design a course cover — a domain entity, built at the source.

    Derived from the ``Course`` (topic + a handful of concept-graph labels + an audience note) and
    the job's ``style_preset``. The subject is drawn from ``topic`` + ``concept_labels`` so the
    cover reads as *this* course (descriptive, not literal), while ``style_preset`` selects the
    medium/mood over the locked house-style constraints. It carries no image bytes and no provider
    detail — it is the brief, not the render.
    """

    topic: str
    concept_labels: tuple[str, ...]
    audience: str
    style_preset: CoverStylePreset
