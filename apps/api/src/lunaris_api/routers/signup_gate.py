from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..dependencies import AdminUserDep, SignupGateServiceDep, require_admin
from ..schemas import SignupGateStatusView, SignupGateUpdate, SignupGateView
from ..signup_gate import InvalidInviteCodeError, SignupGate

router = APIRouter(prefix="/api", tags=["signup-gate"])


def _bind(response: Response) -> None:
    """Bind a fresh correlation id for the request and surface it in X-Request-Id — so a change to
    the signup gate (a security setting) is traceable across the logs."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id


def _to_view(gate: SignupGate) -> SignupGateView:
    return SignupGateView(
        invite_code=gate.invite_code,
        enforced=gate.enforced,
        updated_at=gate.updated_at,
    )


@router.get("/signup-gate", response_model=SignupGateStatusView)
async def get_signup_gate_status(
    service: SignupGateServiceDep, response: Response
) -> SignupGateStatusView:
    """Public (pre-login): whether an invitation code is required to sign up. Carries no code — the
    sign-up form uses it only to show or hide the invite field."""
    _bind(response)
    gate = await service.get()
    return SignupGateStatusView(enforced=gate.enforced)


@router.get(
    "/admin/signup-gate",
    response_model=SignupGateView,
    dependencies=[Depends(require_admin)],
)
async def get_signup_gate(service: SignupGateServiceDep, response: Response) -> SignupGateView:
    """Admin-only: the current shared invite code, the enforced flag, and when it last changed."""
    _bind(response)
    return _to_view(await service.get())


@router.put("/admin/signup-gate", response_model=SignupGateView)
async def update_signup_gate(
    payload: SignupGateUpdate,
    admin_id: AdminUserDep,
    service: SignupGateServiceDep,
    response: Response,
) -> SignupGateView:
    """Admin-only: rotate the code and/or toggle enforcement (each field optional). An empty or
    malformed code is a 400 — never silently stored as a code no one can match."""
    _bind(response)
    try:
        gate = await service.update(
            invite_code=payload.invite_code,
            enforced=payload.enforced,
            updated_by=admin_id,
        )
    except InvalidInviteCodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_view(gate)
