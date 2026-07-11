"""Guard: CoverStylePreset must stay in lockstep with the cover_jobs.style_preset CHECK.

A preset added to the enum but not to the DB CHECK passes every hermetic test (the in-memory queue
has no CHECK) yet fails at runtime the moment a Supabase-backed enqueue stores that preset — a
Postgres constraint violation. Mirrors the BYOK provider lockstep guard, which caught exactly this
class of drift for `openai`.
"""

import re
from pathlib import Path

from lunaris_runtime.schema import CoverStylePreset

_MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
_CHECK = re.compile(
    r"add constraint cover_jobs_style_preset_check\s+check\s*\(\s*style_preset in \(([^)]*)\)",
    re.IGNORECASE,
)


def _current_preset_check() -> set[str]:
    """The preset set admitted by the LATEST migration defining the CHECK (filename order = apply
    order), so a later widening wins."""
    latest: str | None = None
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        for match in _CHECK.finditer(path.read_text()):
            latest = match.group(1)
    assert latest is not None, "no cover_jobs style_preset CHECK found in the migrations"
    return {token.strip().strip("'\"") for token in latest.split(",")}


def test_every_style_preset_is_admitted_by_the_db_check() -> None:
    admitted = _current_preset_check()
    missing = {preset.value for preset in CoverStylePreset} - admitted
    assert not missing, (
        f"CoverStylePreset {sorted(missing)} not in the cover_jobs CHECK {sorted(admitted)}"
        " — add a migration widening cover_jobs_style_preset_check."
    )
