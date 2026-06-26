from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Response

from ..dependencies import AdminUserDep, ProdOpsProviderDep
from ..schemas.prod_ops import CostPointView, CostSeriesView, ProdOpsSummaryView
from ._correlation import bind_correlation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/prod-ops", tags=["admin-prod-ops"])

# The cost/compute window the dashboard opens on, and the bound it may be widened to. 7 days is the
# default view; 90 caps the Azure query (and the chart's density) at something sane.
_DEFAULT_DAYS = 7
_MAX_DAYS = 90
DaysQuery = Annotated[int, Query(ge=1, le=_MAX_DAYS)]


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


@router.get("/cost", response_model=CostSeriesView)
async def get_cost(
    admin_id: AdminUserDep,
    provider: ProdOpsProviderDep,
    response: Response,
    days: DaysQuery = _DEFAULT_DAYS,
) -> CostSeriesView:
    """Admin-only: daily Azure spend for the prod resource group over the last ``days`` days
    (default 7). The most recent day is flagged partial — Cost Management lags ~8-24h."""
    request_id = bind_correlation(response)
    series = await provider.get_cost_daily(days)
    logger.info("prod_ops_cost_fetched", admin_id=admin_id, days=days, request_id=request_id)
    return CostSeriesView(
        currency=series.currency,
        points=[
            CostPointView(day=point.day, amount=point.amount, is_partial=point.partial)
            for point in series.points
        ],
    )
