from dataclasses import dataclass, field

from lunaris_runtime.schema import Resource


@dataclass(frozen=True)
class CuratedResources:
    """A curator's output for one lesson — vetted resources bucketed by Merrill phase (P7.4).

    The transient internal grouping the ``curate_resources`` tool attaches to a lesson's segments;
    each list holds the ``Resource`` contracts the judge assigned to that phase. All four default to
    empty so honest degradation (no source met the bar) is the zero-value, not a special case.
    """

    activate: list[Resource] = field(default_factory=list)
    demonstrate: list[Resource] = field(default_factory=list)
    apply: list[Resource] = field(default_factory=list)
    integrate: list[Resource] = field(default_factory=list)
