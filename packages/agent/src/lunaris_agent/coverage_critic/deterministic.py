"""The deterministic coverage fail-safe (CQ Phase 4.2).

The structural half of the coverage gate: a researched competency is *built* when some module is
tagged with it (the ``competency`` field the architect maps each module to, P7.3). Whatever the
standard promised but no module is tagged with is a gap. Reuses ``framework_coverage`` — the same
split the ``design_curriculum`` tool already logs — so the gate and the build signal agree.

This is the no-key path AND the ``ClaudeCoverageCritic``'s fallback: it can't judge whether prose
*materially* builds a competency (only that a module claims to), but it never needs a model, so a
keyless build still gets an honest, conservative coverage check rather than none.
"""

from lunaris_runtime.schema import Course, CourseBrief

from ..coverage import framework_coverage
from .report import CoverageGap, CoverageReport

_NO_MODULE_REASON = "No module is built around this competency."


class DeterministicCoverageCritic:
    """Flags any researched competency that no module is tagged with — structural, no LLM."""

    async def review(self, course: Course, *, brief: CourseBrief | None) -> CoverageReport:
        research = brief.research if brief is not None else None
        if research is None or not research.competencies:
            return CoverageReport()
        _covered, uncovered = framework_coverage(research, course.modules)
        return CoverageReport(
            [CoverageGap(competency, _NO_MODULE_REASON) for competency in uncovered]
        )
