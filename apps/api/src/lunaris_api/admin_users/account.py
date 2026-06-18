from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminAccount:
    """One end-user account as the admin user-management surface sees it (a Supabase Auth user).

    A read model over GoTrue's user record — only the fields the admin list shows. ``email`` is
    optional because non-email identities exist; ``email_confirmed`` collapses GoTrue's
    ``email_confirmed_at`` timestamp to a flag.
    """

    id: str
    email: str | None
    created_at: datetime | None
    last_sign_in_at: datetime | None
    email_confirmed: bool
