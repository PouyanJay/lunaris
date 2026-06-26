from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..admin_users import AdminAccount
from ..config import Settings, get_settings
from ..dependencies import AdminUserDep, UserDirectoryDep
from ..schemas.admin_users import AdminAccountView
from ._correlation import bind_correlation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _to_view(account: AdminAccount, *, settings: Settings, admin_id: str) -> AdminAccountView:
    return AdminAccountView(
        id=account.id,
        email=account.email,
        created_at=account.created_at,
        last_sign_in_at=account.last_sign_in_at,
        email_confirmed=account.email_confirmed,
        is_admin=settings.is_admin(account.email),
        is_self=account.id == admin_id,
    )


@router.get("", response_model=list[AdminAccountView])
async def list_users(
    admin_id: AdminUserDep,
    directory: UserDirectoryDep,
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> list[AdminAccountView]:
    """Admin-only: every account, with its admin/self flags for the user-management list."""
    bind_correlation(response)
    accounts = await directory.list_accounts()
    return [_to_view(account, settings=settings, admin_id=admin_id) for account in accounts]


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    admin_id: AdminUserDep,
    directory: UserDirectoryDep,
) -> Response:
    """Admin-only: delete an account. ``user_id`` is UUID-typed, so a malformed id is a 422, not a
    500. An admin can't delete their OWN account (a 400) — that would lock them out mid-session;
    otherwise idempotent (204 even if the id is already gone)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    headers = {"X-Request-Id": request_id}
    target = str(user_id)
    if target == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't delete your own account.",
            headers=headers,
        )
    await directory.delete_account(target)
    # Audit the privileged action — ids only, never the target's email (PII stays out of the logs).
    logger.info("admin_user_deleted", target_user_id=target, admin_id=admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)
