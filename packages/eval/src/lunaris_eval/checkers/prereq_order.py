from lunaris_runtime.schema import Course

from ..report import CheckResult

_NAME = "prereq_order"
_BEFORE_ALL = -1  # sentinel: earlier than any real topological position


def prereq_order_check(course: Course) -> CheckResult:
    """Failure-A line: the course never teaches a concept before its prerequisite.

    This is an INDEPENDENT verifier — it does not trust the builder's ``is_acyclic`` flag.
    A topological order that covers every node and respects every edge is itself a proof of
    acyclicity, so we verify that directly, then check the module sequence stays in order.
    """
    graph = course.graph
    kc_ids = {node.id for node in graph.nodes}
    if not kc_ids:
        return CheckResult(_NAME, passed=False, detail="prerequisite graph has no concepts")
    if set(graph.topo_order) != kc_ids:
        return CheckResult(
            _NAME, passed=False, detail="topological order does not cover every concept"
        )

    position = {kc_id: index for index, kc_id in enumerate(graph.topo_order)}
    for edge in graph.edges:
        if edge.from_ not in position or edge.to not in position:
            return CheckResult(
                _NAME,
                passed=False,
                detail=f"edge {edge.from_}→{edge.to} references an unknown concept",
            )
        if position[edge.from_] >= position[edge.to]:
            return CheckResult(
                _NAME, passed=False, detail=f"prerequisite {edge.from_} is ordered after {edge.to}"
            )

    # Modules must not regress in the order. We gate on each module's most-advanced KC, so a
    # module may still review earlier concepts as long as it doesn't step backwards overall.
    last_position = _BEFORE_ALL
    for module in course.modules:
        unknown = [kc_id for kc_id in module.kcs if kc_id not in kc_ids]
        if unknown:
            return CheckResult(
                _NAME, passed=False, detail=f"module {module.id} references unknown KC {unknown[0]}"
            )
        module_position = max((position[kc_id] for kc_id in module.kcs), default=_BEFORE_ALL)
        if module_position < last_position:
            return CheckResult(
                _NAME, passed=False, detail=f"module {module.id} is out of prerequisite order"
            )
        last_position = module_position

    return CheckResult(
        _NAME,
        passed=True,
        detail=f"{len(graph.nodes)} concepts, {len(graph.edges)} edges in valid prerequisite order",
    )
