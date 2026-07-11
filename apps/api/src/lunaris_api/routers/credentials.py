import structlog
from fastapi import APIRouter, HTTPException, status

from ..credential_vault import CredentialVault, UnknownProviderError
from ..dependencies import CredentialVaultDep, CurrentUserIdDep
from ..schemas import CredentialStatusView, CredentialTestResult, SecretValue
from ..secrets import CredentialStatus, SecretValidationError

# Structured audit trail for BYOK key operations (provider + outcome ONLY — never a value, never
# last4). Added after a production incident where the decisive question — "did a save for provider X
# ever reach the API, and what happened to it?" — could only be answered by piecing together uvicorn
# access lines; these events make it one Log Analytics query.
logger = structlog.get_logger()

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

_BYOK_UNAVAILABLE = "Bring-your-own-key storage is not configured on this server."


def _require_vault(vault: CredentialVault | None) -> CredentialVault:
    """Fail closed with a 503 when BYOK is unconfigured (no master key), so the client shows a clear
    'unavailable' state rather than a confusing empty success."""
    if vault is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_BYOK_UNAVAILABLE
        )
    return vault


def _to_view(status_: CredentialStatus) -> CredentialStatusView:
    return CredentialStatusView(
        provider=status_.provider, is_set=status_.is_set, last4=status_.last4
    )


@router.get("", response_model=list[CredentialStatusView])
async def list_credentials(
    user_id: CurrentUserIdDep, vault: CredentialVaultDep
) -> list[CredentialStatusView]:
    """The caller's BYOK key surface: every provider's set/unset state + last4 — never a value."""
    statuses = await _require_vault(vault).statuses(user_id=user_id)
    return [_to_view(s) for s in statuses]


@router.put("/{provider}", response_model=CredentialStatusView)
async def set_credential(
    provider: str, payload: SecretValue, user_id: CurrentUserIdDep, vault: CredentialVaultDep
) -> CredentialStatusView:
    """Store (or rotate) the caller's key for a provider. The key is probed, encrypted, and saved;
    only the masked status is returned. 404 unknown provider; 400 empty/invalid or rejected key."""
    try:
        result = await _require_vault(vault).set(
            user_id=user_id, provider=provider, value=payload.value.get_secret_value()
        )
    except UnknownProviderError as exc:
        logger.warning("credential_save_unknown_provider", provider=provider)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}"
        ) from exc
    except (ValueError, SecretValidationError) as exc:
        # The messages are value-free (no key echoed); the value is never logged either.
        logger.warning("credential_save_rejected", provider=provider, reason=type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    logger.info("credential_saved", provider=provider)
    return _to_view(result)


@router.delete("/{provider}", response_model=CredentialStatusView)
async def delete_credential(
    provider: str, user_id: CurrentUserIdDep, vault: CredentialVaultDep
) -> CredentialStatusView:
    """Remove the caller's key for a provider (idempotent). Returns the now-unset status. 404 for an
    unknown provider."""
    try:
        await _require_vault(vault).delete(user_id=user_id, provider=provider)
    except UnknownProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}"
        ) from exc
    logger.info("credential_deleted", provider=provider)
    return CredentialStatusView(provider=provider, is_set=False, last4=None)


@router.post("/{provider}/test", response_model=CredentialTestResult)
async def test_credential(
    provider: str, payload: SecretValue, user_id: CurrentUserIdDep, vault: CredentialVaultDep
) -> CredentialTestResult:
    """Probe a key's validity WITHOUT storing it (the Settings 'Test' button). A probe is a query:
    a rejected key is a 200 with ``ok=false`` + a safe detail, not an error. 404 unknown provider;
    400 only for a malformed (empty/control-char) value."""
    try:
        await _require_vault(vault).test(provider=provider, value=payload.value.get_secret_value())
    except UnknownProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SecretValidationError as exc:
        logger.info("credential_probe", provider=provider, ok=False)
        return CredentialTestResult(ok=False, detail=str(exc))
    logger.info("credential_probe", provider=provider, ok=True)
    return CredentialTestResult(ok=True)
