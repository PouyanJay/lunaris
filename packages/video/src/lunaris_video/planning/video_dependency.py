from collections.abc import Iterable
from dataclasses import dataclass

from lunaris_runtime.schema import Course, Edge

from lunaris_video.models.video_dependency_map import VideoDependencyMap


def project_video_dependencies(course: Course) -> VideoDependencyMap:
    """Project ``Course.graph`` (the KC prerequisite DAG) down to a lesson-video dependency map.

    A lesson video depends on another lesson video iff a knowledge component the first teaches has a
    (transitive) prerequisite among the second's — following ``Edge.from_`` (must be learned before)
    ``→ to`` edges. Lessons map to KCs via their module's ``kcs``; same-module lessons share KCs, so
    they never become each other's upstream (the cross-module prerequisite is the real dependency).
    Upstream lists and the overall ``order`` follow the graph's topological teaching order. An
    un-graphed course (no edges) yields no dependencies — every lesson a root, in appearance order.
    """
    index = _index_lessons(course)
    prereqs = _prereqs_of(course.graph.edges)
    topo = {kc: position for position, kc in enumerate(course.graph.topo_order)}
    rank = {
        lesson_id: _topo_rank(index.lesson_kcs[lesson_id], topo, index.appearance[lesson_id])
        for lesson_id in index.lesson_kcs
    }
    upstream = {
        lesson_id: tuple(sorted(_upstream_lessons(lesson_id, index, prereqs), key=rank.__getitem__))
        for lesson_id in index.lesson_kcs
    }
    order = tuple(sorted(index.lesson_kcs, key=rank.__getitem__))
    return VideoDependencyMap(upstream=upstream, order=order)


@dataclass(frozen=True)
class _LessonIndex:
    """The lesson↔KC↔module wiring the projection needs, indexed once over the course's modules."""

    lesson_kcs: dict[str, frozenset[str]]  # lesson id → the KCs it teaches (its module's)
    lesson_module: dict[str, str]  # lesson id → its module id (for same-module exclusion)
    kc_lessons: dict[str, set[str]]  # KC → the lessons that teach it
    appearance: dict[str, int]  # lesson id → its order of appearance (a stable tiebreaker)


def _index_lessons(course: Course) -> _LessonIndex:
    lesson_kcs: dict[str, frozenset[str]] = {}
    lesson_module: dict[str, str] = {}
    kc_lessons: dict[str, set[str]] = {}
    appearance: dict[str, int] = {}
    for module in course.modules:
        module_kcs = frozenset(module.kcs)
        for lesson in module.lessons:
            lesson_kcs[lesson.id] = module_kcs
            lesson_module[lesson.id] = module.id
            appearance[lesson.id] = len(appearance)
            for kc in module_kcs:
                kc_lessons.setdefault(kc, set()).add(lesson.id)
    return _LessonIndex(lesson_kcs, lesson_module, kc_lessons, appearance)


def _prereqs_of(edges: Iterable[Edge]) -> dict[str, set[str]]:
    # An edge from_ → to means from_ must be learned before to, so from_ is a prerequisite of to.
    prereqs: dict[str, set[str]] = {}
    for edge in edges:
        prereqs.setdefault(edge.to, set()).add(edge.from_)
    return prereqs


def _ancestors(kcs: frozenset[str], prereqs: dict[str, set[str]]) -> set[str]:
    # Every (transitive) prerequisite of these KCs — a DFS backwards along the prereq edges. The
    # ``seen`` set also makes an accidental cycle terminate (finite, not infinite) despite acyclic.
    seen: set[str] = set()
    stack = [prereq for kc in kcs for prereq in prereqs.get(kc, ())]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(prereqs.get(current, ()))
    return seen


def _upstream_lessons(
    lesson_id: str, index: _LessonIndex, prereqs: dict[str, set[str]]
) -> set[str]:
    kcs = index.lesson_kcs[lesson_id]
    upstream_kcs = _ancestors(kcs, prereqs) - kcs  # never depend on a KC this lesson itself teaches
    lessons = {lesson for kc in upstream_kcs for lesson in index.kc_lessons.get(kc, set())}
    lessons.discard(lesson_id)
    # Same-module lessons share KCs, so a prereq edge never distinguishes them — drop them; the real
    # dependency is the cross-module prerequisite.
    same_module = index.lesson_module[lesson_id]
    return {lesson for lesson in lessons if index.lesson_module[lesson] != same_module}


def _topo_rank(kcs: frozenset[str], topo: dict[str, int], appearance: int) -> tuple[int, int]:
    # A lesson's topological position is the earliest teaching index among its KCs; KCs missing from
    # topo_order (and KC-less lessons) sink past every ordered one, then appearance breaks ties.
    unordered = len(topo) + 1
    position = min((topo.get(kc, unordered) for kc in kcs), default=unordered)
    return (position, appearance)
