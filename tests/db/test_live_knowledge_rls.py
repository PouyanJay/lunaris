"""Live-database proof of the ``live_knowledge`` RLS posture (Lunaris Live, Phase 2a).

This table records what a person does and does not understand, and — more sharply than the others —
what it says is *acted on*: the director gates every introduction on it. So the write posture
matters as much as the read one. A learner who could set their own mastery could skip the entire
curriculum, and the belief is only meaningful because the grader is the only thing that sets it.

Same harness and gating as the sibling suites: eval-marked, ``SUPABASE_DB_URL``-gated, one
rolled-back transaction per test.
"""

import os
import uuid
from collections.abc import Callable

import pytest

psycopg = pytest.importorskip("psycopg")

_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _DB_URL, reason="SUPABASE_DB_URL not set (needs a live database)"),
]

_AsUser = Callable[["psycopg.Cursor", str], None]


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _believe(cur: "psycopg.Cursor", owner: str, graph_id: str, node_id: str = "a") -> None:
    """Record a belief the way the grader does — service_role, bypassing RLS."""
    cur.execute(
        """
        insert into public.live_knowledge
            (user_id, graph_id, node_id, estimate, evidence_count, last_evidence_turn)
        values (%s, %s, %s, 0.45, 1, 1)
        """,
        (owner, graph_id, node_id),
    )


def test_a_learner_sees_only_their_own_beliefs(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — two learners on the same map, so only the policy can separate them.
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_user(db, mine)
    _seed_user(db, theirs)
    _believe(db, mine, "g1")
    _believe(db, theirs, "g1")

    # Act
    as_user(db, mine)
    db.execute("select user_id from public.live_knowledge")

    # Assert
    assert [str(row[0]) for row in db.fetchall()] == [mine]


def test_a_learner_cannot_declare_their_own_mastery(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """The load-bearing one. The director gates every introduction on this number, so a learner who
    could write it could skip the curriculum — and the eval would still call the session a success.
    """
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _believe(db, owner, "g1")


def test_a_learner_cannot_raise_a_belief_the_grader_set(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — a real belief of this learner's, so only the grant can refuse.
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.live_knowledge set estimate = 1.0 where user_id = %s", (owner,))


def test_a_learner_cannot_forget_an_inconvenient_belief(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    """Deleting is the same attack as writing, in reverse: a concept with no belief looks like one
    never taught, so the director would re-introduce it instead of remediating."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.live_knowledge where user_id = %s", (owner,))


def test_anon_reaches_nothing(db: "psycopg.Cursor") -> None:
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")

    # Act
    db.execute("set local role anon")

    # Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select estimate from public.live_knowledge")


def test_truncate_is_not_reachable_by_a_user(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """TRUNCATE is a privilege RLS cannot police, so the revoke has to have caught it."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("truncate public.live_knowledge")


def test_a_belief_outside_the_probability_range_is_refused(db: "psycopg.Cursor") -> None:
    """The Python side clamps, but the column is the backstop — and this is the value the director
    compares against thresholds, so a number outside [0, 1] would silently disable a rule."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)

    # Act / Assert — service_role bypasses RLS but not a check constraint.
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            """
            insert into public.live_knowledge
                (user_id, graph_id, node_id, estimate) values (%s, 'g1', 'a', 1.5)
            """,
            (owner,),
        )


def test_one_learner_holds_one_belief_per_concept_per_map(db: "psycopg.Cursor") -> None:
    """The natural key. Two rows for one concept would make "what do they know" ambiguous, and the
    loop upserts on exactly this key — without the constraint it would append instead."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")

    # Act / Assert
    with pytest.raises(psycopg.errors.UniqueViolation):
        _believe(db, owner, "g1")


def test_the_same_concept_id_on_another_map_is_a_different_belief(db: "psycopg.Cursor") -> None:
    """Node ids are graph-local, so "a" on one map and "a" on another are unrelated — the graph_id
    in the key is the only thing keeping them apart."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")

    # Act — the same concept id on a different map inserts cleanly.
    _believe(db, owner, "g2")

    # Assert
    db.execute("select count(*) from public.live_knowledge where user_id = %s", (owner,))
    assert db.fetchone()[0] == 2


def test_a_claim_rides_the_belief_and_a_learner_cannot_write_one(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    """P2c T3: the placement interview's claim about a concept is a nullable column beside the
    belief. Written by the server (a claim seeds a row with no evidence), readable by its owner,
    and NOT writable by them: a learner who could set a prior could tilt Tier 2's band on a say-so
    (the director would still check the claim before crediting it, but the write path is the
    server's regardless)."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    db.execute(
        """
        insert into public.live_knowledge
            (user_id, graph_id, node_id, estimate, evidence_count, last_evidence_turn, prior)
        values (%s, 'g1', 'a', 0.0, 0, 0, 0.8)
        """,
        (owner,),
    )
    as_user(db, owner)

    db.execute("select prior from public.live_knowledge where user_id = %s", (owner,))
    assert db.fetchone() == (0.8,)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.live_knowledge set prior = 1.0 where user_id = %s", (owner,))


def test_a_claim_outside_the_probability_range_is_refused(db: "psycopg.Cursor") -> None:
    owner = str(uuid.uuid4())
    _seed_user(db, owner)

    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            """
            insert into public.live_knowledge
                (user_id, graph_id, node_id, estimate, prior) values (%s, 'g1', 'a', 0.0, 1.5)
            """,
            (owner,),
        )


def test_a_learner_can_read_their_review_day_and_cannot_move_it(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    """P2c T6: the review ladder rides the belief (rung + next review day). Written by the server at
    a session's close, readable by its owner (the close shows it), and NOT writable by them: a
    learner who could set their own review day could postpone every check indefinitely."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    db.execute(
        """
        insert into public.live_knowledge
            (user_id, graph_id, node_id, estimate, evidence_count, last_evidence_turn,
             review_stage, due_at)
        values (%s, 'g1', 'a', 0.7, 2, 2, 2, '2026-08-21T12:00:00+00')
        """,
        (owner,),
    )
    as_user(db, owner)

    db.execute(
        "select review_stage, due_at::text from public.live_knowledge where user_id = %s", (owner,)
    )
    assert db.fetchone() == (2, "2026-08-21 12:00:00+00")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(
            "update public.live_knowledge set due_at = '2030-01-01' where user_id = %s", (owner,)
        )


@pytest.mark.parametrize("rung", [-1, 8], ids=["below the ladder", "above its top"])
def test_a_rung_off_the_ladder_is_refused(db: "psycopg.Cursor", rung: int) -> None:
    """Both ends: the ladder grows geometrically, so a rung above the top (found in review) is as
    much a corrupt row as one below the bottom — the Python side stops climbing at the same rung."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)

    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            """
            insert into public.live_knowledge
                (user_id, graph_id, node_id, estimate, review_stage) values (%s, 'g1', 'a', 0.0, %s)
            """,
            (owner, rung),
        )


def test_a_belief_written_before_the_schedule_reads_as_unscheduled(db: "psycopg.Cursor") -> None:
    """The expand-only promise: a row the previous release wrote (no rung, no day) is on rung
    zero with no review, which is what "never scheduled" means to the director."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _believe(db, owner, "g1")

    db.execute(
        "select review_stage, due_at from public.live_knowledge where user_id = %s", (owner,)
    )
    assert db.fetchone() == (0, None)
