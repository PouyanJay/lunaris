from contextlib import AbstractContextManager, nullcontext

from .credential_resolver import CredentialResolver
from .run_credentials import run_credentials


async def credentials_for(
    resolver: CredentialResolver | None, owner_id: str | None
) -> AbstractContextManager[None]:
    """The credential scope a piece of work on ``owner_id``'s behalf should run in.

    The tenant's own keys when there is a resolver and an owner (BYOK), else a no-op that leaves the
    work reading the process environment. One function rather than a resolve-then-scope pair per
    caller: the compile plane, the session plane and the material prefetcher each held their own
    copy of the same two lines, and the property they all need — a tenant's work is billed on the
    tenant's key, never the platform's — is one property (extracted at the third copy, P2c T4).

    An EMPTY vault is not the same as BYOK being off: a tenant who has set no keys gets a scope
    with nothing in it, so their work reads no key rather than the platform's — the graph plane's
    rule (pinned by its cost tests), which the session plane had drifted from before this helper.

    Awaited before the ``with``, deliberately: the resolver does I/O, and a context manager cannot.
    """
    if resolver is None or owner_id is None:
        return nullcontext()
    return run_credentials(await resolver(owner_id))
