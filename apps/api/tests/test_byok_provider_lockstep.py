"""Guard: BYOK_PROVIDERS must stay in lockstep with the provider_credentials.provider CHECK.

A provider added to ``BYOK_PROVIDERS`` (and ``KNOWN_SECRETS``) but NOT to the DB CHECK constraint
passes every hermetic test (the in-memory credential store has no CHECK) yet fails at runtime the
moment a Supabase-backed tenant saves that key — a Postgres constraint violation. This static test
parses the current CHECK out of the migrations and asserts every BYOK provider is admitted, so the
drift is caught in `pytest`, not in production. (Added after the Phase-1 review caught exactly this
gap for `openai`.)
"""

import re
from pathlib import Path

from lunaris_api.secrets.credential_store_protocol import BYOK_PROVIDERS
from lunaris_api.secrets.store import KNOWN_SECRETS

_MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
# `add constraint provider_credentials_provider_check ... check (provider in ('a', 'b', ...))`
_CHECK = re.compile(
    r"add constraint provider_credentials_provider_check\s+check\s*\(\s*provider in \(([^)]*)\)",
    re.IGNORECASE,
)


def _current_provider_check() -> set[str]:
    """The provider set admitted by the LATEST migration that redefines the CHECK (filename order =
    apply order), so a later widening wins over the original create-table constraint."""
    latest: str | None = None
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        for match in _CHECK.finditer(path.read_text()):
            latest = match.group(1)
    assert latest is not None, "no provider_credentials CHECK found in the migrations"
    return {token.strip().strip("'\"") for token in latest.split(",")}


def test_every_byok_provider_is_admitted_by_the_db_check() -> None:
    admitted = _current_provider_check()
    missing = set(BYOK_PROVIDERS) - admitted
    assert not missing, (
        f"BYOK_PROVIDERS {sorted(missing)} not in the provider_credentials CHECK {sorted(admitted)}"
        " — add a migration widening the constraint (mirror provider_credentials_add_*.sql)."
    )


def test_every_byok_provider_has_a_known_secret_env_var() -> None:
    # The other half of the lockstep: a BYOK provider must map to an env var the runtime reads.
    missing = set(BYOK_PROVIDERS) - set(KNOWN_SECRETS)
    assert not missing, f"BYOK_PROVIDERS {sorted(missing)} missing from KNOWN_SECRETS"


_CREDENTIALS_PANEL = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "web"
    / "src"
    / "components"
    / "settings"
    / "CredentialsPanel.tsx"
)
# `provider: "anthropic",` — one entry per key the Keys UI renders an input for.
_WEB_PROVIDER = re.compile(r"provider:\s*[\"']([^\"']+)[\"']")


def test_every_byok_provider_is_offered_by_the_web_keys_ui() -> None:
    """The third leg of the lockstep: a provider the API accepts but the WEB never renders an input
    for is a key the tenant can NEVER supply — silently un-storable.

    This is not hypothetical: ``openai`` was added to BYOK_PROVIDERS + the DB CHECK for AI course
    covers, but never to the web PROVIDERS list, so the Keys UI offered no OpenAI field. With no way
    to store the key, ``useOpenAiKeyPresent`` stayed false forever and the cover-images toggle was
    permanently disabled — the feature was unreachable in the product despite shipping end to end.
    """
    offered = set(_WEB_PROVIDER.findall(_CREDENTIALS_PANEL.read_text()))
    missing = set(BYOK_PROVIDERS) - offered
    assert not missing, (
        f"BYOK_PROVIDERS {sorted(missing)} are not offered by the web Keys UI {sorted(offered)}"
        f" — add an entry to PROVIDERS in {_CREDENTIALS_PANEL.name}, else it can never be set."
    )
