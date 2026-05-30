from lunaris_runtime.schema import Course

from .checkers import factuality_check, fit_check, prereq_order_check
from .report import EvalReport


def evaluate_course(course: Course) -> EvalReport:
    """Run every deterministic quality check against a course and aggregate the verdict."""
    return EvalReport(
        checks=(
            prereq_order_check(course),
            fit_check(course),
            factuality_check(course),
        )
    )
