"""The cost stores' own SQL, against a live database.

``test_cost_subject_rls.py`` proves the *schema*: the composite key, the grants, the policies. It
writes its own INSERTs, though, so it says nothing about the queries the production stores actually
build — and those are what runs in production. Two defects that this suite exists to catch both slip
past every other test in the repo: an upsert whose conflict target is wrong (the rollup silently
stops updating), and a read that drops ``subject_type`` on the way back (a graph's cost reported as
a course's).

Gated on the REST credentials rather than ``SUPABASE_DB_URL``: these drive the supabase-py client,
not psycopg. Rows are written for real — there is no enclosing transaction to roll back — so each
test purges what it created.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from lunaris_runtime.persistence import SupabaseCostEventStore, SupabaseSubjectCostStore
from lunaris_runtime.schema import CostEvent, CostPocket, CostProvider, CostSubjectType, SubjectCost

_URL = os.environ.get("SUPABASE_URL", "")
_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not (_URL and _KEY),
        reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set (needs a live database)",
    ),
]


@pytest.fixture
async def subject() -> AsyncIterator[str]:
    """A fresh subject id, purged from both tables afterwards whatever the test did."""
    subject_id = f"t-{uuid.uuid4().hex}"
    yield subject_id
    for kind in CostSubjectType:
        await SupabaseCostEventStore().delete_for_subject(subject_type=kind, subject_id=subject_id)
        await SupabaseSubjectCostStore().delete_for_subject(
            subject_type=kind, subject_id=subject_id
        )


def _event(subject_id: str, *, kind: CostSubjectType, seq: int, amount: float) -> CostEvent:
    return CostEvent(
        run_id=f"run-{uuid.uuid4().hex}",
        subject_type=kind,
        subject_id=subject_id,
        seq=seq,
        component="compile",
        provider=CostProvider.ANTHROPIC,
        model="claude-opus-4-8",
        pocket=CostPocket.PLATFORM,
        usage={"input_tokens": 100},
        amount=amount,
        currency="USD",
        price_book_version="v-test",
    )


def _rollup(subject_id: str, *, kind: CostSubjectType, total: float) -> SubjectCost:
    return SubjectCost(
        subject_type=kind,
        subject_id=subject_id,
        total_amount=total,
        currency="USD",
        breakdown={"eventCount": 1},
        price_book_version="v-test",
        updated_at=datetime.now(UTC),
    )


async def test_a_graph_s_spend_survives_the_round_trip_as_a_graph_s(subject: str) -> None:
    """Subject fidelity through the real queries.

    A read that dropped ``subject_type`` — defaulting everything to ``course`` on the way back —
    would be invisible to every in-memory test in the repo, and would report a Live graph's spend
    as a course's on the one endpoint a learner actually reads.
    """
    # Arrange
    ledger, rollup = SupabaseCostEventStore(), SupabaseSubjectCostStore()

    # Act
    await ledger.append(
        events=[_event(subject, kind=CostSubjectType.LIVE_GRAPH, seq=0, amount=2.5)]
    )
    await rollup.upsert(cost=_rollup(subject, kind=CostSubjectType.LIVE_GRAPH, total=2.5))

    # Assert
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id=subject
    )
    assert [(e.subject_type, e.subject_id, e.amount) for e in events] == [
        (CostSubjectType.LIVE_GRAPH, subject, 2.5)
    ]
    stored = await rollup.get(subject_type=CostSubjectType.LIVE_GRAPH, subject_id=subject)
    assert stored is not None
    assert stored.subject_type is CostSubjectType.LIVE_GRAPH
    assert stored.total_amount == 2.5

    # ...and it is not reachable as a course, which is the collision the key exists to prevent.
    assert (await rollup.get(subject_type=CostSubjectType.COURSE, subject_id=subject)) is None
    assert (
        await ledger.list_for_subject(subject_type=CostSubjectType.COURSE, subject_id=subject) == []
    )


async def test_a_recompute_replaces_the_rollup_instead_of_failing(subject: str) -> None:
    """Every finished job recomputes a subject's total. If the upsert's conflict target does not
    match the row already there, Postgres attempts an insert, hits a unique constraint, and the
    recorder *swallows* the error — so the total silently freezes at whatever it was."""
    # Arrange
    rollup = SupabaseSubjectCostStore()
    await rollup.upsert(cost=_rollup(subject, kind=CostSubjectType.LIVE_GRAPH, total=1.0))

    # Act
    await rollup.upsert(cost=_rollup(subject, kind=CostSubjectType.LIVE_GRAPH, total=7.0))

    # Assert
    stored = await rollup.get(subject_type=CostSubjectType.LIVE_GRAPH, subject_id=subject)
    assert stored is not None and stored.total_amount == 7.0


async def test_a_rollup_written_by_the_previous_release_is_healed_not_stranded(
    subject: str,
) -> None:
    """The deploy window, exactly as it happens.

    CD pushes migrations before it rolls the image, so for a few seconds the previous release is
    still creating rollup rows — with ``on_conflict=course_id`` and no subject columns at all,
    leaving ``subject_id`` NULL. The new store then recomputes that same course. If its upsert
    keyed on the new columns, that row would not match, Postgres would fall through to an INSERT,
    and the still-live primary key on ``course_id`` would reject it — a failure the recorder
    swallows, freezing that course's total for good.
    """
    # Arrange — a row shaped the way the previous release writes it.
    import psycopg

    db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        pytest.skip("SUPABASE_DB_URL not set (needed to write a pre-migration-shaped row)")
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            """
            insert into public.course_costs
                (course_id, total_amount, currency, breakdown, price_book_version)
            values (%s, 2.0, 'USD', '{}'::jsonb, 'v-old')
            """,
            (subject,),
        )

    # Act — the new release recomputes the same course.
    rollup = SupabaseSubjectCostStore()
    await rollup.upsert(cost=_rollup(subject, kind=CostSubjectType.COURSE, total=5.0))

    # Assert — updated in place, and the subject columns are now filled in.
    stored = await rollup.get(subject_type=CostSubjectType.COURSE, subject_id=subject)
    assert stored is not None, "the old-shaped row was stranded instead of healed"
    assert stored.total_amount == 5.0
