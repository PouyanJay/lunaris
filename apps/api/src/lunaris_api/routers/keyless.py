from fastapi import APIRouter
from lunaris_runtime.capabilities import CAPABILITY_SPECS
from lunaris_runtime.resilience import ReadinessStatus, probe_keyless_llm_endpoint
from lunaris_runtime.schema import CapabilityName

from ..dependencies import CredentialVaultDep, OptionalUserIdDep, SecretStoreDep
from ..schemas import KeylessReadinessView

router = APIRouter(prefix="/api/keyless", tags=["keyless"])

# The LLM capability's secret id — its presence means the caller's LLM is a hosted API (no local
# server to provision). Read from the shared capability table so it can't drift from the badge/tag.
_LLM_SECRET_ID = next(s.secret_id for s in CAPABILITY_SPECS if s.capability is CapabilityName.LLM)


async def _llm_is_keyed(
    owner_id: str | None, vault: CredentialVaultDep, store: SecretStoreDep
) -> bool:
    """Whether the caller's LLM provider key is set — tenant-aware, mirroring /api/capabilities: the
    caller's BYOK vault when auth + a vault are present, else the operator file store."""
    if vault is not None and owner_id is not None:
        statuses = await vault.statuses(user_id=owner_id)
        return any(s.provider == _LLM_SECRET_ID and s.is_set for s in statuses)
    return any(s.name == _LLM_SECRET_ID and s.is_set for s in store.statuses())


@router.get("/readiness", response_model=KeylessReadinessView)
async def get_keyless_readiness(
    owner_id: OptionalUserIdDep,
    vault: CredentialVaultDep,
    store: SecretStoreDep,
) -> KeylessReadinessView:
    """Whether the keyless model endpoint can serve right now, so the web can show a
    "Provisioning…" state on a keyless build instead of a silent wait.

    A caller whose LLM is keyed gets ``not_applicable`` (a hosted API — no local server), and the
    endpoint does NOT probe (so it never needlessly wakes a non-existent server). A keyless caller
    gets the live health probe: ``ready`` / ``provisioning`` (waking or loading) / ``unreachable``.
    """
    if await _llm_is_keyed(owner_id, vault, store):
        return KeylessReadinessView(status=ReadinessStatus.NOT_APPLICABLE.value)
    status = await probe_keyless_llm_endpoint()
    return KeylessReadinessView(status=status.value)
