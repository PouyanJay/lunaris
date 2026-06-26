import structlog
from fastapi import APIRouter, Response

from ..dependencies import AdminUserDep, ProdOpsProviderDep
from ..schemas.prod_ops import ProdOpsSummaryView
from ._correlation import bind_correlation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/prod-ops", tags=["admin-prod-ops"])


@router.get("/summary", response_model=ProdOpsSummaryView)
async def get_summary(
    admin_id: AdminUserDep,
    provider: ProdOpsProviderDep,
    response: Response,
) -> ProdOpsSummaryView:
    """Admin-only: the prod-operations overview (covered resource group + billing currency)."""
    request_id = bind_correlation(response)
    summary = await provider.get_summary()
    # Audit the privileged read — admin id only, never any secret/PII.
    logger.info("prod_ops_summary_fetched", admin_id=admin_id, request_id=request_id)
    return ProdOpsSummaryView(
        resource_group=summary.resource_group,
        currency=summary.currency,
    )
