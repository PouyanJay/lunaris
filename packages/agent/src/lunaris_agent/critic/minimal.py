from itertools import pairwise

from lunaris_runtime.schema import Course, VerifierStatus

from ..lesson_claims import iter_claims

_MERRILL_PHASES = ("activate", "demonstrate", "apply", "integrate")


class MinimalCritic:
    """The MVP pedagogy critic (build-spec §05): deterministic structural rubric checks.

    Re-verifies the invariants the upstream agents are each responsible for — so a bug in
    any one of them is caught at the gate rather than shipping. Checks: a valid acyclic
    graph, module KCs that exist in the graph, non-decreasing module difficulty, every
    module taught by a lesson with all four Merrill phases, every objective targeting a
    real KC and backed by an assessment item, and the claim publish gate (no live
    unsupported claim). Returns one human-readable string per violation; empty == clean.
    """

    def review(self, course: Course) -> list[str]:
        issues: list[str] = []
        kc_ids = {node.id for node in course.graph.nodes}

        if not course.graph.is_acyclic:
            issues.append("prerequisite graph is not acyclic")
        if course.goal_concept and course.goal_concept not in kc_ids:
            issues.append(f"goal concept {course.goal_concept!r} is not a graph node")

        issues.extend(self._review_module_difficulty(course))
        issues.extend(self._review_modules(course, kc_ids))
        issues.extend(self._review_claims(course))
        return issues

    def _review_module_difficulty(self, course: Course) -> list[str]:
        issues: list[str] = []
        for earlier, later in pairwise(course.modules):
            if later.difficulty_index < earlier.difficulty_index:
                issues.append(f"module difficulty decreases: {earlier.id} > {later.id}")
        return issues

    def _review_modules(self, course: Course, kc_ids: set[str]) -> list[str]:
        issues: list[str] = []
        for module in course.modules:
            for kc_id in module.kcs:
                if kc_id not in kc_ids:
                    issues.append(f"module {module.id!r} references unknown KC {kc_id!r}")
            if not module.lessons:
                issues.append(f"module {module.id!r} has no lesson")
            for lesson in module.lessons:
                missing = [
                    phase for phase in _MERRILL_PHASES if not getattr(lesson.segments, phase)
                ]
                if missing:
                    issues.append(
                        f"lesson {lesson.id!r} is missing Merrill phase(s): {', '.join(missing)}"
                    )
            for objective in module.objectives:
                if objective.kc not in kc_ids:
                    issues.append(f"objective in {module.id!r} targets unknown KC {objective.kc!r}")
                if not objective.assessed_by:
                    issues.append(
                        f"objective for KC {objective.kc!r} in {module.id!r} has no assessment item"
                    )
        return issues

    def _review_claims(self, course: Course) -> list[str]:
        lessons = [lesson for module in course.modules for lesson in module.lessons]
        live_unsupported = [
            claim.text
            for claim in iter_claims(lessons)
            if claim.supported_by is None and claim.verifier_status is not VerifierStatus.CUT
        ]
        return [
            f"publish gate violated: live unsupported claim {text!r}" for text in live_unsupported
        ]
