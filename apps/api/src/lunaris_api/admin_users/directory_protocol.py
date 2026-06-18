from typing import Protocol

from .account import AdminAccount


class IUserDirectory(Protocol):
    """The end-user account directory the admin surface reads and manages.

    Backed in production by the Supabase Auth admin API (service-role); an in-memory fake covers
    the no-DB/test path. ``list_accounts`` returns every account; ``delete_account`` removes one by
    id (idempotent — deleting an absent id is not an error).
    """

    async def list_accounts(self) -> list[AdminAccount]: ...

    async def delete_account(self, user_id: str) -> None: ...
