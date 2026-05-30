from lunaris_runtime.schema import Course

from ..report import CheckResult

_NAME = "fit"


def fit_check(course: Course) -> CheckResult:
    """The course starts at the learner's frontier and ends at the goal concept.

    A novice (empty frontier) must start at a graph root (a concept with no prerequisites);
    a learner with a frontier must start on it. The goal must be the most-advanced concept:
    last in the topological order, with nothing depending on it.
    """
    graph = course.graph
    if not graph.topo_order:
        return CheckResult(_NAME, passed=False, detail="course has no concepts")
    if not course.goal_concept:
        return CheckResult(_NAME, passed=False, detail="course has no goal concept")

    frontier = set(graph.frontier)
    has_incoming = {edge.to for edge in graph.edges}
    has_outgoing = {edge.from_ for edge in graph.edges}
    start = graph.topo_order[0]

    if frontier:
        if start not in frontier:
            return CheckResult(
                _NAME, passed=False, detail=f"path starts at {start}, not on the learner's frontier"
            )
    elif start in has_incoming:  # novice path: the first concept must be a root
        return CheckResult(
            _NAME, passed=False, detail=f"novice path starts at {start}, which has prerequisites"
        )

    if graph.topo_order[-1] != course.goal_concept:
        return CheckResult(
            _NAME, passed=False, detail=f"goal {course.goal_concept} is not the final concept"
        )
    if course.goal_concept in has_outgoing:
        return CheckResult(
            _NAME,
            passed=False,
            detail=f"goal {course.goal_concept} is a prerequisite for a later concept",
        )

    return CheckResult(
        _NAME, passed=True, detail=f"starts at {start}, ends at goal {course.goal_concept}"
    )
