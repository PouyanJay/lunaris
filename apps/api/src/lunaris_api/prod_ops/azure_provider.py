import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple

import httpx
import structlog

from .arm_client import ArmClient
from .compute import ComputePoint, ComputeSeries
from .cost import CostPoint, CostSeries
from .governed_resources import GovernedResources
from .power import PowerState, ResourcePower
from .power_action_error import ProdPowerActionError
from .power_state_unavailable_error import ProdPowerStateUnavailableError
from .power_status import PowerStatus
from .resource_kind import ResourceKind
from .summary import ProdOpsSummary

_ARM = "https://management.azure.com"
_COST_API = "2023-11-01"
_METRICS_API = "2024-02-01"
_APP_API = "2024-03-01"
_VM_API = "2024-07-01"
_GB = 1024**3

logger = structlog.get_logger()

# A container app's ARM ``runningStatus`` (lower-cased). ``Progressing`` is an in-flight start/stop;
# anything else Azure reports maps to UNKNOWN.
_APP_STATUS = {
    "running": PowerStatus.RUNNING,
    "stopped": PowerStatus.STOPPED,
    "progressing": PowerStatus.TRANSITIONING,
}

# A virtual machine's ``PowerState/*`` instance-view code. ``stopped`` is powered off but still
# allocated, so it keeps billing for compute: not a settled OFF (the switch's OFF deallocates it).
_VM_STATUS = {
    "PowerState/running": PowerStatus.RUNNING,
    "PowerState/deallocated": PowerStatus.STOPPED,
    "PowerState/stopped": PowerStatus.TRANSITIONING,
    "PowerState/starting": PowerStatus.TRANSITIONING,
    "PowerState/stopping": PowerStatus.TRANSITIONING,
    "PowerState/deallocating": PowerStatus.TRANSITIONING,
}

# What a failed ARM exchange can raise: an HTTP or transport error, or a malformed body/token.
_ARM_FAILURES = (httpx.HTTPError, ValueError, KeyError)


def _parse_usage_date(raw: object) -> date:
    """Cost Management returns the day as an int ``YYYYMMDD`` (or sometimes an ISO string)."""
    text = str(raw)[:10].replace("-", "")
    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


def _iso_z(value: datetime) -> str:
    """A UTC datetime as ``...Z`` (never ``+00:00`` — the ``+`` becomes a space in a URL query)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _PowerAction(NamedTuple):
    """One start/stop call: which resource, which ARM action, and where to send it."""

    resource: str
    verb: str
    url: str
    api_version: str


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
        governed: GovernedResources,
        currency: str = "CAD",
    ) -> None:
        self._arm = arm
        self._sub = subscription_id
        self._rg = resource_group
        if api_app not in governed.container_apps:
            raise ValueError(f"The API app {api_app!r} must be one of the governed container apps.")
        self._api_app = api_app
        self._apps = governed.container_apps
        self._vms = governed.virtual_machines
        self._currency = currency

    @property
    def _rg_scope(self) -> str:
        return f"/subscriptions/{self._sub}/resourceGroups/{self._rg}"

    def _app_id(self, app: str) -> str:
        return f"{_ARM}{self._rg_scope}/providers/Microsoft.App/containerApps/{app}"

    def _vm_id(self, vm: str) -> str:
        return f"{_ARM}{self._rg_scope}/providers/Microsoft.Compute/virtualMachines/{vm}"

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
        # Use a trailing 'Z' for UTC, NOT isoformat()'s '+00:00': the '+' in a URL query string
        # decodes to a space, so ARM reads an invalid ISO-8601 interval and 400s the whole query.
        timespan = f"{_iso_z(start)}/{_iso_z(end)}"
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
        reads = [self._app_power(app) for app in self._apps] + [
            self._vm_power(vm) for vm in self._vms
        ]
        try:
            found = await asyncio.gather(*reads)
        except _ARM_FAILURES as exc:
            raise ProdPowerStateUnavailableError from exc
        # A governed VM that is not deployed (no simulators in this environment) is simply absent.
        resources = tuple(r for r in found if r is not None)
        api_running = any(r.name == self._api_app and r.running for r in resources)
        return PowerState(is_on=api_running, resources=resources)

    async def _app_power(self, app: str) -> ResourcePower:
        # Container apps are required: a missing one is a misconfiguration, so it raises.
        payload = await self._arm.request(
            "GET", self._app_id(app), params={"api-version": _APP_API}
        )
        running_status = str(payload.get("properties", {}).get("runningStatus", "")).lower()
        return ResourcePower(
            name=app,
            kind=ResourceKind.CONTAINER_APP,
            status=_APP_STATUS.get(running_status, PowerStatus.UNKNOWN),
        )

    async def _vm_power(self, vm: str) -> ResourcePower | None:
        # The power state lives only in the instance view; expanding it on the plain GET needs just
        # virtualMachines/read (no separate instanceView permission).
        payload = await self._arm.request_if_exists(
            "GET", self._vm_id(vm), params={"api-version": _VM_API, "$expand": "instanceView"}
        )
        if payload is None:
            return None
        statuses = payload.get("properties", {}).get("instanceView", {}).get("statuses", [])
        codes = (str(status.get("code", "")) for status in statuses)
        power_code = next((code for code in codes if code.startswith("PowerState/")), "")
        return ResourcePower(
            name=vm,
            kind=ResourceKind.VIRTUAL_MACHINE,
            status=_VM_STATUS.get(power_code, PowerStatus.UNKNOWN),
        )

    async def set_power(self, *, on: bool) -> PowerState:
        # Sequential on purpose: the actions are issued in the order _power_actions defines.
        failed: list[str] = []
        for action in self._power_actions(on=on):
            if not await self._act(action):
                failed.append(action.resource)
        if failed:
            raise ProdPowerActionError(on=on, failed=tuple(failed))
        return await self.get_power_state()

    def _power_actions(self, *, on: bool) -> list[_PowerAction]:
        """The start/stop calls in issue order. ARM accepts each one at once (202) and completes it
        in the background, so this orders when work is requested, not when it finishes: going down,
        the API is asked to stop first so it stops accepting new work before the workers go, and the
        VM last; coming up, the VM (the slowest to boot) is asked first and the API last."""
        api = [app for app in self._apps if app == self._api_app]
        workers = [app for app in self._apps if app != self._api_app]
        if on:
            return [_PowerAction(vm, "start", self._vm_id(vm), _VM_API) for vm in self._vms] + [
                _PowerAction(app, "start", self._app_id(app), _APP_API) for app in workers + api
            ]
        # Deallocate, never power off: a powered-off VM keeps billing for its compute.
        return [_PowerAction(app, "stop", self._app_id(app), _APP_API) for app in api + workers] + [
            _PowerAction(vm, "deallocate", self._vm_id(vm), _VM_API) for vm in self._vms
        ]

    async def _act(self, action: _PowerAction) -> bool:
        """Send one start/stop call; False (logged) when it fails, so the remaining resources are
        still attempted. A governed VM that is not deployed counts as done."""
        url = f"{action.url}/{action.verb}"
        params = {"api-version": action.api_version}
        try:
            if action.api_version == _VM_API:
                await self._arm.request_if_exists("POST", url, params=params)
            else:
                await self._arm.request("POST", url, params=params)
        except _ARM_FAILURES as exc:
            response = getattr(exc, "response", None)
            logger.warning(
                "prod_power_action_failed",
                resource=action.resource,
                action=action.verb,
                status_code=getattr(response, "status_code", None),
                error_type=type(exc).__name__,
            )
            return False
        return True
