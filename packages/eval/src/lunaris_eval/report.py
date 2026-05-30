from dataclasses import dataclass

# The MVP definition of done: a course passes iff its prerequisite ordering and its
# factuality both hold (Phase 0 §11). Other checks are reported but not DoD-gating.
_DOD_CHECKS = frozenset({"prereq_order", "factuality"})


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a single deterministic quality check."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvalReport:
    """The aggregate of every check run against one course-object."""

    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        """True iff every check passed."""
        return all(check.passed for check in self.checks)

    @property
    def meets_dod(self) -> bool:
        """True iff the DoD-gating checks (prereq-order + factuality) ran AND passed.

        Requiring them to be present avoids a vacuous pass if a future runner drops one.
        """
        present = {check.name for check in self.checks if check.name in _DOD_CHECKS}
        return present == _DOD_CHECKS and all(
            check.passed for check in self.checks if check.name in _DOD_CHECKS
        )
