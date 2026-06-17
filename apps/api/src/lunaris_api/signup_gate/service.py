from ..secrets import contains_control_characters
from .errors import InvalidInviteCodeError
from .gate import SignupGate
from .store_protocol import ISignupGateStore

# A shared invite code is short by nature; cap it so an admin can't store an unbounded blob.
_MAX_CODE_LENGTH = 128


class SignupGateService:
    """The admin-facing signup-gate surface: read the current state, rotate the code, toggle
    enforcement. A partial update keeps whichever field the caller omitted. The code is validated
    (non-empty after trimming, bounded, no control characters) before it is persisted.
    """

    def __init__(self, store: ISignupGateStore) -> None:
        self._store = store

    async def get(self) -> SignupGate:
        return await self._store.get()

    async def update(
        self,
        *,
        invite_code: str | None = None,
        enforced: bool | None = None,
        updated_by: str | None = None,
    ) -> SignupGate:
        current = await self._store.get()
        # Nothing to change → don't write (so an empty PUT can't churn updated_at/updated_by).
        if invite_code is None and enforced is None:
            return current
        next_code = current.invite_code if invite_code is None else _clean_code(invite_code)
        next_enforced = current.enforced if enforced is None else enforced
        return await self._store.save(
            SignupGate(invite_code=next_code, enforced=next_enforced),
            updated_by=updated_by,
        )


def _clean_code(raw: str) -> str:
    code = raw.strip()
    if not code:
        raise InvalidInviteCodeError("The invitation code must not be empty.")
    if len(code) > _MAX_CODE_LENGTH:
        raise InvalidInviteCodeError(
            f"The invitation code must be at most {_MAX_CODE_LENGTH} characters."
        )
    if contains_control_characters(code):
        raise InvalidInviteCodeError("The invitation code must not contain control characters.")
    return code
