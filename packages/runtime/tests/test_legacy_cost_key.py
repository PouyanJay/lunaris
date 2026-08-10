"""The transitional value written into the cost tables' legacy ``course_id`` column.

Short-lived code, but not unimportant: the rollup's primary key is still on that column for one
deploy, so whatever goes in it has to stay unique across subject types *and* across subjects. A
collision here is not a wrong number on a screen — it is a unique violation the recorder swallows,
leaving a subject whose rollup silently never gets written.
"""

from lunaris_runtime.persistence.legacy_cost_key import legacy_course_id
from lunaris_runtime.schema import CostSubjectType

_MAX_LENGTH = 100


def test_a_course_keeps_the_id_the_previous_release_reads() -> None:
    """Byte-identical, deliberately: during a deploy the old code is still selecting these rows by
    this value. Anything else would hide a course's cost from the release that is still serving."""
    assert legacy_course_id(CostSubjectType.COURSE, "course-abc") == "course-abc"


def test_a_graph_is_namespaced_so_it_cannot_land_on_a_course_s_id() -> None:
    # The collision the composite key exists to prevent, in the one column that cannot express it.
    shared = "0123456789abcdef"
    assert legacy_course_id(CostSubjectType.LIVE_GRAPH, shared) != legacy_course_id(
        CostSubjectType.COURSE, shared
    )


def test_two_long_ids_that_share_a_prefix_do_not_collide() -> None:
    """The reason this hashes instead of truncating.

    Slicing an over-long value to fit the column would map every id sharing the first ~89
    characters onto one legacy value — trading the collision this function exists to remove for a
    subtler one, surfacing as a rollup that never gets written.
    """
    # Arrange — identical for the whole length the column could hold, differing only past it.
    stem = "g" * 120
    first, second = f"{stem}-one", f"{stem}-two"

    # Act
    left = legacy_course_id(CostSubjectType.LIVE_GRAPH, first)
    right = legacy_course_id(CostSubjectType.LIVE_GRAPH, second)

    # Assert
    assert left != right
    assert len(left) <= _MAX_LENGTH and len(right) <= _MAX_LENGTH


def test_the_value_always_fits_the_column() -> None:
    """The column's own check constraint is 1..100; overrunning it is a failed insert, and cost
    writes are best-effort — so it would be a silent loss rather than a loud one."""
    for subject_id in ("x", "y" * 32, "z" * 100, "w" * 500):
        value = legacy_course_id(CostSubjectType.LIVE_GRAPH, subject_id)
        assert 1 <= len(value) <= _MAX_LENGTH


def test_the_same_id_always_maps_to_the_same_value() -> None:
    """A rollup is upserted repeatedly as jobs finish. A value that varied between calls would
    append rows instead of replacing one."""
    long_id = "q" * 200
    assert legacy_course_id(CostSubjectType.LIVE_GRAPH, long_id) == legacy_course_id(
        CostSubjectType.LIVE_GRAPH, long_id
    )
