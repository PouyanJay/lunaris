from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SignupGate:
    """The signup invite-gate state: the shared code and whether it is enforced.

    ``invite_code`` is the plaintext shared secret — server-only: the admin reads it to hand out,
    but non-admins and the pre-login SPA never see it. ``enforced`` False means the gate is open
    (any signup allowed). ``updated_at`` is None for a never-persisted value; the store stamps it on
    save and on read from the DB.
    """

    invite_code: str
    enforced: bool
    updated_at: datetime | None = None
