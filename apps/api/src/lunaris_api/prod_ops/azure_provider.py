import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .arm_client import ArmClient
from .compute import ComputePoint, ComputeSeries
from .cost import CostPoint, CostSeries
from .power import AppPower, PowerState
from .summary import ProdOpsSummary

_ARM = "https://management.azure.com"
_COST_API = "2023-11-01"
_METRICS_API = "2024-02-01"
_APP_API = "2024-03-01"
_GB = 1024**3


def _parse_usage_date(raw: object) -> date:
    """Cost Management returns the day as an int ``YYYYMMDD`` (or sometimes an ISO string)."""
    text = str(raw)[:10].replace("-", "")
    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


class AzureProdOpsProvider:
    """The real ``IProdOpsProvider`` — reads/controls prod via Azure ARM through the API's managed
    identity (``ArmClient``). Cost from Cost Management, compute from Azure Monitor metrics, power
    from the container apps' run state + start/stop actions. Constructed only in cloud, where the
    identity has Cost Management Reader + Monitoring Reader on the resource group; the in-memory
    fake covers the local/test path, so this class is exercised by contract tests, not live in CI.
    """

    def __init__(
        self,
        arm: ArmClient,
        *,
        subscription_id: str,
        resource_group: str,
        api_app: str,
        governed_apps: Sequence[str],
        currency: str = "CAD",
    ) -> None:
        self._arm = arm
        self._sub = subscription_id
        self._rg = resource_group
        self._api_app = api_app
        self._apps = tuple(governed_apps)
        self._currency = currency

    @property
    def _rg_scope(self) -> str:
        return f"/subscriptions/{self._sub}/resourceGroups/{self._rg}"

    def _app_id(self, app: str) -> str:
        return f"{_ARM}{self._rg_scope}/providers/Microsoft.App/containerApps/{app}"

    async def get_summary(self) -> ProdOpsSummary:
        return ProdOpsSummary(resource_group=self._rg, currency=self._currency)

    async def get_cost_daily(self, days: int) -> CostSeries:
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": f"{start}T00:00:00Z", "to": f"{today}T23:59:59Z"},
            "dataset": {
                "granularity": "Daily",
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            },
        }
        url = f"{_ARM}{self._rg_scope}/providers/Microsoft.CostManagement/query"
        payload = await self._arm.request("POST", url, params={"api-version": _COST_API}, json=body)
        props = payload.get("properties", {})
        columns = [c.get("name") for c in props.get("columns", [])]
        cost_i = columns.index("Cost") if "Cost" in columns else 0
        date_i = columns.index("UsageDate") if "UsageDate" in columns else 1
        cur_i = columns.index("Currency") if "Currency" in columns else None
        by_day: dict[date, float] = {}
        currency = self._currency
        for row in props.get("rows", []):
            day = _parse_usage_date(row[date_i])
            by_day[day] = by_day.get(day, 0.0) + float(row[cost_i])
            if cur_i is not None:
                currency = str(row[cur_i])
        points = tuple(
            CostPoint(
                day=start + timedelta(days=i),
                amount=round(by_day.get(start + timedelta(days=i), 0.0), 2),
                partial=(start + timedelta(days=i) == today),
            )
            for i in range(days)
        )
        return CostSeries(points=points, currency=currency)

    async def get_compute_series(self, days: int) -> ComputeSeries:
        # Issues N+1 ARM reads: one Azure Monitor metrics call per governed app (run concurrently)
        # plus one Cost Management query (amortized into the hourly cost line).
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=days * 24 - 1)
        timespan = f"{start.isoformat()}/{end.isoformat()}"
        replicas: dict[datetime, float] = {}
        cores: dict[datetime, float] = {}
        memory: dict[datetime, float] = {}
        payloads = await asyncio.gather(*(self._fetch_metrics(app, timespan) for app in self._apps))
        for payload in payloads:
            for metric in payload.get("value", []):
                name = metric.get("name", {}).get("value")
                series = metric.get("timeseries") or [{}]
                for entry in series[0].get("data", []):
                    hour = datetime.fromisoformat(entry["timeStamp"].replace("Z", "+00:00"))
                    value = float(entry.get("average") or 0.0)
                    if name == "Replicas":
                        replicas[hour] = replicas.get(hour, 0.0) + value
                    elif name == "UsageNanoCores":
                        cores[hour] = cores.get(hour, 0.0) + value / 1e9
                    elif name == "WorkingSetBytes":
                        memory[hour] = memory.get(hour, 0.0) + value / _GB
        cost = await self._hourly_cost(start.date(), end.date())
        hours = sorted(set(replicas) | set(cores) | set(memory) | set(cost))
        points = tuple(
            ComputePoint(
                hour=hour,
                replicas=round(replicas.get(hour, 0.0), 2),
                cpu_cores=round(cores.get(hour, 0.0), 3),
                memory_gb=round(memory.get(hour, 0.0), 2),
                cost=round(cost.get(hour, 0.0), 4),
            )
            for hour in hours
        )
        return ComputeSeries(points=points, currency=self._currency)

    async def _fetch_metrics(self, app: str, timespan: str) -> dict[str, Any]:
        return await self._arm.request(
            "GET",
            f"{self._app_id(app)}/providers/microsoft.insights/metrics",
            params={
                "api-version": _METRICS_API,
                "metricnames": "Replicas,UsageNanoCores,WorkingSetBytes",
                "timespan": timespan,
                "interval": "PT1H",
                "aggregation": "Average",
            },
        )

    async def _hourly_cost(self, start: date, end: date) -> dict[datetime, float]:
        # Cost Management bills daily for ActualCost; amortize each day's spend evenly across its 24
        # hours so the compute chart's cost line aligns with the usage bars.
        series = await self.get_cost_daily((end - start).days + 1)
        spread: dict[datetime, float] = {}
        for point in series.points:
            base = datetime.combine(point.day, datetime.min.time(), tzinfo=UTC)
            for hour in range(24):
                spread[base + timedelta(hours=hour)] = point.amount / 24
        return spread

    async def get_power_state(self) -> PowerState:
        apps = []
        for app in self._apps:
            payload = await self._arm.request(
                "GET", self._app_id(app), params={"api-version": _APP_API}
            )
            running_status = payload.get("properties", {}).get("runningStatus", "")
            apps.append(AppPower(name=app, running=running_status.lower() == "running"))
        api_running = next((a.running for a in apps if a.name == self._api_app), False)
        return PowerState(is_on=api_running, apps=tuple(apps))

    async def set_power(self, *, on: bool) -> PowerState:
        action = "start" if on else "stop"
        for app in self._apps:
            await self._arm.request(
                "POST", f"{self._app_id(app)}/{action}", params={"api-version": _APP_API}
            )
        return await self.get_power_state()
