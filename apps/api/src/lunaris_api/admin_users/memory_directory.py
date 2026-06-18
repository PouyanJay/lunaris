from collections.abc import Iterable

from .account import AdminAccount


class InMemoryUserDirectory:
    """In-process account directory — the no-DB/CI fallback and test stub. Seeded with a fixed set
    of accounts; ``delete_account`` removes by id (idempotent)."""

    def __init__(self, accounts: Iterable[AdminAccount] | None = None) -> None:
        self._accounts: list[AdminAccount] = list(accounts) if accounts is not None else []

    async def list_accounts(self) -> list[AdminAccount]:
        return list(self._accounts)

    async def delete_account(self, user_id: str) -> None:
        self._accounts = [account for account in self._accounts if account.id != user_id]
