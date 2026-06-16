from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoDependencyMap:
    """The course's lesson videos projected to a dependency DAG from its prerequisite graph.

    For each lesson video, ``upstream`` holds the upstream lesson videos it depends on — the lessons
    whose knowledge components are (transitive) prerequisites of this lesson's, projected from
    ``Course.graph`` to the lesson grain — in topological teaching order. ``order`` is every lesson
    video in that same topological order (the generation order: upstream before downstream).

    Derived from the real prerequisite edges + ``Module.kcs``, never from positional sequence. It
    drives the planner's upstream-sibling context today, and the generation order later.
    """

    upstream: Mapping[str, tuple[str, ...]]
    order: tuple[str, ...]

    def upstream_of(self, lesson_id: str) -> tuple[str, ...]:
        """The upstream lesson videos ``lesson_id`` builds on, in topo order — () for a root."""
        return self.upstream.get(lesson_id, ())
