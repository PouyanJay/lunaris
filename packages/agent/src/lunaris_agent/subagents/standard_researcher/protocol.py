from typing import Protocol

from lunaris_runtime.schema import CourseBrief, StandardResearch


class IStandardResearcher(Protocol):
    """Grounds a brief's target standard in real competencies + provenance (P7.2 research stage).

    Given the interpreted brief, runs a bounded, best-effort research step — search the standard's
    authoritative sources, fetch + extract them, and distil the actual competency descriptors and
    any score/threshold lines — so extraction and the curriculum design backward from the real
    standard rather than the model's approximate memory. Swappable (live researcher vs. a stub that
    returns preconfigured findings), like every other subagent collaborator, and degrades honestly
    (``UNAVAILABLE``) when no source is reachable.
    """

    async def research(self, brief: CourseBrief) -> StandardResearch: ...
