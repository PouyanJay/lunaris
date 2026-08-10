import asyncio
import os
from datetime import datetime

from lunaris_runtime.schema import CostSubjectType, SubjectCost

from .guard import guard
from .legacy_cost_key import legacy_course_id

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "course_costs"
_COLUMNS = (
    "subject_type, subject_id, total_amount, currency, breakdown, price_book_version, updated_at"
)


class SupabaseSubjectCostStore:
    """The production cost rollup: Supabase Postgres, lazy service-role client.

    The rollup twin of ``SupabaseCostEventStore``: one row per subject, upserted on
    ``(subject_type, subject_id)`` each time a job finishes. The service-role client bypasses
    RLS (the table is owner-scoped by
    RLS, so a user-JWT client could only ever reach its own rows even if it queried directly), and
    every query is additionally scoped by ``user_id`` in app code. The synchronous supabase-py calls
    run off the event loop via ``asyncio.to_thread``; the client is built lazily on first use.
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot store costs"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("subject_costs upsert")
    async def upsert(self, *, cost: SubjectCost, owner_id: str | None = None) -> None:
        client = self._ensure_client()
        row = {
            "subject_type": cost.subject_type.value,
            "subject_id": cost.subject_id,
            # Written for as long as the column exists — see legacy_course_id.
            "course_id": legacy_course_id(cost.subject_type, cost.subject_id),
            "total_amount": cost.total_amount,
            "currency": cost.currency,
            "breakdown": cost.breakdown,
            "price_book_version": cost.price_book_version,
            "updated_at": cost.updated_at.isoformat(),
            **({"user_id": owner_id} if owner_id is not None else {}),
        }
        # The arbiter stays on the LEGACY column for as long as that column exists, even though the
        # real key is now (subject_type, subject_id). During a deploy the previous release creates
        # rollup rows with `on_conflict=course_id` and no subject columns at all, leaving
        # subject_id NULL. A new-key arbiter would not match such a row, so Postgres would attempt
        # an INSERT and hit the still-live primary key on course_id — a unique violation that
        # `finalize` swallows, freezing that course's total for good. Upserting on the column both
        # releases agree about matches instead, and the update carries the subject columns, so an
        # old-shaped row is healed on its next recompute rather than stranded. `legacy_course_id`
        # is what keeps this arbiter unique across subject types. Moves to (subject_type,
        # subject_id) in the contract migration, when no old-shaped writer is left.
        await asyncio.to_thread(
            lambda: client.table(_TABLE).upsert(row, on_conflict="course_id").execute()  # type: ignore[attr-defined]
        )

    @guard("subject_costs get")
    async def get(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> SubjectCost | None:
        client = self._ensure_client()

        def _run() -> object:
            query = (
                client.table(_TABLE)
                .select(_COLUMNS)
                .eq("subject_type", subject_type.value)
                .eq("subject_id", subject_id)
            )  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # another user's rollup reads as absent
            return query.limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []  # type: ignore[attr-defined]
        return self._to_subject_cost(rows[0]) if rows else None

    @guard("subject_costs delete")
    async def delete_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> int:
        client = self._ensure_client()

        def _run() -> object:
            query = (
                client.table(_TABLE)
                .delete(count="exact")
                .eq("subject_type", subject_type.value)
                .eq("subject_id", subject_id)
            )  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only purge the caller's own rollup
            return query.execute()

        response = await asyncio.to_thread(_run)
        return response.count or 0

    @staticmethod
    def _to_subject_cost(row: dict[str, object]) -> SubjectCost:
        return SubjectCost(
            subject_type=CostSubjectType(str(row["subject_type"])),
            subject_id=str(row["subject_id"]),
            total_amount=float(row["total_amount"]),  # type: ignore[arg-type]
            currency=str(row["currency"]),
            breakdown=row["breakdown"],  # type: ignore[arg-type]
            price_book_version=str(row["price_book_version"]),
            # datetime.fromisoformat parses a trailing Z natively on py3.11+ (matches
            # SupabaseRunStore._to_course_run's inline parse — one timestamp convention, not two).
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
