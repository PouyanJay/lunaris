from typing import Protocol

from .gate import SignupGate


class ISignupGateStore(Protocol):
    """Storage for the singleton signup-gate row (the shared invite code + enforced flag).

    Exactly one logical row exists per deployment. ``get`` always returns a value — a fail-open
    default when the row is absent — so a read never raises. ``save`` upserts the singleton and
    returns the persisted state with a fresh ``updated_at``. Backends: an in-memory fallback
    (no-DB/tests) and a Supabase service-role store (production; the table is RLS-locked, reachable
    only by service_role and the auth hook).
    """

    async def get(self) -> SignupGate: ...

    async def save(self, gate: SignupGate, *, updated_by: str | None = None) -> SignupGate: ...
