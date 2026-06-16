from lunaris_runtime.schema import Course

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

    # KC prerequisites: an edge from_ → to means from_ must be learned before to, so from_ is a
    # prerequisite of to. ``ancestors`` walks these backwards for the transitive prerequisite set.
    prereqs_of: dict[str, set[str]] = {}
    for edge in course.graph.edges:
        prereqs_of.setdefault(edge.to, set()).add(edge.from_)

    def ancestors(kc: str) -> set[str]:
        seen: set[str] = set()
        stack = list(prereqs_of.get(kc, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(prereqs_of.get(current, ()))
        return seen

    # A lesson's topological position is the earliest teaching index among its KCs; KCs missing from
    # topo_order (and KC-less lessons) sink to the end, after every ordered one.
    topo_index = {kc: i for i, kc in enumerate(course.graph.topo_order)}
    unordered = len(topo_index) + 1

    def sort_key(lesson_id: str) -> tuple[int, int]:
        kcs = lesson_kcs[lesson_id]
        position = min((topo_index.get(kc, unordered) for kc in kcs), default=unordered)
        return (position, appearance[lesson_id])

    upstream: dict[str, tuple[str, ...]] = {}
    for lesson_id, kcs in lesson_kcs.items():
        upstream_kcs: set[str] = set()
        for kc in kcs:
            upstream_kcs |= ancestors(kc)
        upstream_kcs -= kcs  # never depend on a KC this lesson itself teaches
        upstream_lessons: set[str] = set()
        for kc in upstream_kcs:
            upstream_lessons |= kc_lessons.get(kc, set())
        upstream_lessons.discard(lesson_id)
        # Same-module lessons share KCs, so a prereq edge never distinguishes them — drop them; the
        # real dependency is the cross-module prerequisite.
        same_module = lesson_module[lesson_id]
        upstream_lessons = {u for u in upstream_lessons if lesson_module[u] != same_module}
        upstream[lesson_id] = tuple(sorted(upstream_lessons, key=sort_key))

    order = tuple(sorted(lesson_kcs, key=sort_key))
    return VideoDependencyMap(upstream=upstream, order=order)
