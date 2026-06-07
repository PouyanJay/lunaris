from typing import Protocol

from lunaris_runtime.schema import Course, CourseBrief

from .report import CoverageReport


class ICoverageCritic(Protocol):
    """Verifies every promised competency is materially built by the course (CQ Phase 4.2).

    The third, additive gate at finalize — distinct from the two it must not touch: the claim
    ``Verifier`` (per-claim grounding, the moat) and the structural ``MinimalCritic`` (sync rubric
    checks). This one maps each researched competency to the content AND practice that builds it and
    returns the gaps ("promised but not built"); ``finalize_course`` turns a gap into an honest
    scope cut + a review flag.

    ``review`` is async + brief-aware because the primary impl is an LLM judge that reads the course
    against the brief's researched framework; a deterministic fail-safe keeps keyless builds going.
    An empty/None brief.research (the no-standard path) yields a clean report — there is nothing
    promised to leave unbuilt.
    """

    async def review(self, course: Course, *, brief: CourseBrief | None) -> CoverageReport: ...
