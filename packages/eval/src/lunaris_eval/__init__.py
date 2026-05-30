"""Lunaris eval — deterministic quality checks against the MVP definition of done.

The harness measures a produced course-object: prerequisite ordering (Failure-A), fit
(starts at the frontier, ends at the goal), and factuality (the claim publish gate,
Failure-B). The DoD gate is prereq-order + factuality. An LLM-as-judge standards rubric
and a multi-topic LangSmith eval set are the live layer (deferred — need a key + budget).
"""

from .checkers import factuality_check, fit_check, prereq_order_check
from .report import CheckResult, EvalReport
from .runner import evaluate_course

__all__ = [
    "CheckResult",
    "EvalReport",
    "evaluate_course",
    "factuality_check",
    "fit_check",
    "prereq_order_check",
]
