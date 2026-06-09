from typing import Annotated

from fastapi import APIRouter, Depends

from ..capabilities import CapabilityStatus, resolve_capabilities
from ..config import Settings, get_settings
from ..dependencies import CredentialVaultDep, OptionalUserIdDep, SecretStoreDep
from ..schemas import CapabilityStatusView

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def _to_view(status_: CapabilityStatus) -> CapabilityStatusView:
    return CapabilityStatusView(
        capability=status_.capability,
        mode=status_.mode,
        provider=status_.provider,
        compute=status_.compute.value if status_.compute is not None else None,
    )


@router.get("", response_model=list[CapabilityStatusView])
async def get_capabilities(
    owner_id: OptionalUserIdDep,
    vault: CredentialVaultDep,
    store: SecretStoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CapabilityStatusView]:
    """Which provider each key-gated capability is using RIGHT NOW: its keyed provider (live) or its
    keyless local fallback. The web shows a Draft badge per fallback capability; a capability flips
    to live the moment its key is stored.

    Tenant-aware: with BYOK on and an authenticated caller, it reads the caller's own credential
    presence (the keys they've set); otherwise it reads the process-wide file secret store
    (single-user / admin). Only set/unset is read — never a key value.
    """
    if vault is not None and owner_id is not None:
        statuses = await vault.statuses(user_id=owner_id)
        set_names = {s.provider for s in statuses if s.is_set}
    else:
        set_names = {s.name for s in store.statuses() if s.is_set}
    resolved = resolve_capabilities(
        lambda name: name in set_names, compute=settings.keyless_compute
    )
    return [_to_view(c) for c in resolved]
