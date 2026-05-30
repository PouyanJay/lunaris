import argparse
import sys
from pathlib import Path

from lunaris_runtime.schema import Course
from pydantic import ValidationError

from .runner import evaluate_course

_PASS = "PASS"
_FAIL = "FAIL"
_USAGE_ERROR = 2


def main() -> int:
    """Evaluate a course-object JSON against the MVP definition of done.

    Exit code 0 iff the DoD-gating checks (prereq-order + factuality) pass, so the harness
    can gate CI. Prints a per-check report to stdout.
    """
    parser = argparse.ArgumentParser(
        prog="lunaris-eval",
        description="Run deterministic quality checks against a course-object JSON.",
    )
    parser.add_argument("course", type=Path, help="path to a course-object JSON file")
    args = parser.parse_args()

    try:
        raw = args.course.read_text()
    except OSError as error:
        print(f"error: cannot read {args.course}: {error}", file=sys.stderr)
        return _USAGE_ERROR
    try:
        course = Course.model_validate_json(raw)
    except ValidationError as error:
        print(f"error: {args.course} is not a valid course object: {error}", file=sys.stderr)
        return _USAGE_ERROR

    report = evaluate_course(course)

    print(f"Course: {course.id}  ({course.topic})")
    for check in report.checks:
        marker = _PASS if check.passed else _FAIL
        print(f"  [{marker}] {check.name}: {check.detail}")
    verdict = _PASS if report.meets_dod else _FAIL
    print(f"DoD (prereq-order + factuality): {verdict}")
    return 0 if report.meets_dod else 1


if __name__ == "__main__":
    sys.exit(main())
