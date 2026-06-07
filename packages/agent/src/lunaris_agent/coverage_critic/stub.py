from lunaris_runtime.schema import Course, CourseBrief

from .report import CoverageReport


class StubCoverageCritic:
    """A no-op coverage critic: every course passes clean (no gap).

    The offline test default — keeps the finalize seam wired (the COVERAGE_VERIFIED stage emits)
    without any LLM call or structural judgement. Production uses the deterministic fail-safe
    (``DeterministicCoverageCritic``) or the LLM judge (``ClaudeCoverageCritic``); this stub exists
    so tests that aren't exercising coverage build a clean course unchanged.
    """

    async def review(self, course: Course, *, brief: CourseBrief | None) -> CoverageReport:
        return CoverageReport()
