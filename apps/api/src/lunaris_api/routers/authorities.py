from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Query, Response, status
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.schema import SubjectField

from ..dependencies import AuthorityStoreDep, OptionalUserIdDep
from ..schemas import SourceAuthorityRequest, SourceAuthorityView

router = APIRouter(prefix="/api/source-authorities", tags=["source-authorities"])

# The trust config steers every build's credibility floor, so with auth on these routes require a
# signed-in caller (OptionalUserIdDep 401s anonymous requests) — an unauthenticated stranger must
# not be able to rewrite which domains a build trusts. The table itself is still GLOBAL (one config
# per deployment, no user_id column): per-tenant trust config is a future migration, so for now any
# authenticated user shares — and can edit — the deployment-wide config. Auth off stays open, like
# every other surface.


def _bind() -> str:
    """Bind a fresh correlation id for the request and return it (for the X-Request-Id header)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    return request_id


@router.get("", response_model=list[SourceAuthorityView])
async def list_authorities(
    store: AuthorityStoreDep, owner_id: OptionalUserIdDep, response: Response
) -> list[SourceAuthorityView]:
    """List the trust-config rows (spine + field packs + denylist) for the Trusted-sources UI."""
    response.headers["X-Request-Id"] = _bind()
    authorities = await store.list_all()
    return [SourceAuthorityView.of(authority) for authority in authorities]


@router.put("", response_model=SourceAuthorityView)
async def upsert_authority(
    payload: SourceAuthorityRequest,
    store: AuthorityStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> SourceAuthorityView:
    """Add or replace a trust-config row (identity is ``(domain, field)``); idempotent upsert."""
    response.headers["X-Request-Id"] = _bind()
    authority = payload.to_model()
    await store.upsert(authority)
    return SourceAuthorityView.of(authority)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_authority(
    store: AuthorityStoreDep,
    owner_id: OptionalUserIdDep,
    domain: Annotated[str, Query(min_length=1, max_length=253)],
    field: Annotated[SubjectField | None, Query()] = None,
) -> Response:
    """Remove a trust-config row by its ``(domain, field)`` key. Idempotent: 204 even if absent."""
    request_id = _bind()
    await store.delete(domain.strip().lower(), field)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})
