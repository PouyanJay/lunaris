from dataclasses import replace
from datetime import UTC, datetime

from .gate import SignupGate

# Mirrors the migration seed so no-DB/dev behaviour matches production's initial state.
_DEFAULT_GATE = SignupGate(invite_code="LUNARIS-BETA", enforced=True)


class InMemorySignupGateStore:
    """In-process signup-gate store — the no-DB/CI fallback and test stub.

    State lives only for the process lifetime (lost on restart); durable storage requires the
    Supabase store. Seeded to match the migration so behaviour is identical with or without a DB.
    """

    def __init__(self, initial: SignupGate | None = None) -> None:
        self._gate = initial if initial is not None else _DEFAULT_GATE

    async def get(self) -> SignupGate:
        return self._gate

    async def save(self, gate: SignupGate, *, updated_by: str | None = None) -> SignupGate:
        # updated_by is part of the durable contract (the DB stamps it) but irrelevant in-process.
        self._gate = replace(gate, updated_at=datetime.now(UTC))
        return self._gate
