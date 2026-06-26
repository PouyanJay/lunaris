"""Contract tests for the real Azure ARM prod-ops adapter.

No live Azure: an ``httpx.MockTransport`` stands in for the managed-identity token endpoint and ARM,
so we verify the adapter issues the right requests (cost query, metrics, container-app run state,
start/stop actions) and parses the responses. The live behaviour is validated at deploy.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from lunaris_api.prod_ops import ArmClient, AzureProdOpsProvider

_TODAY = datetime.now(UTC).date()
_YESTERDAY = _TODAY - timedelta(days=1)


def _arm_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "identity.local":
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    path = request.url.path
    if path.endswith("/Microsoft.CostManagement/query"):
        return httpx.Response(
            200,
            json={
                "properties": {
                    "columns": [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "Currency"}],
                    "rows": [
                        [3.5, int(_YESTERDAY.strftime("%Y%m%d")), "CAD"],
                        [1.0, int(_TODAY.strftime("%Y%m%d")), "CAD"],
                    ],
                }
            },
        )
    if path.endswith("/microsoft.insights/metrics"):
        stamp = f"{_TODAY.isoformat()}T00:00:00Z"
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "name": {"value": "Replicas"},
                        "timeseries": [{"data": [{"timeStamp": stamp, "average": 1.0}]}],
                    },
                    {
                        "name": {"value": "UsageNanoCores"},
                        "timeseries": [{"data": [{"timeStamp": stamp, "average": 5e8}]}],
                    },
                    {
                        "name": {"value": "WorkingSetBytes"},
                        "timeseries": [{"data": [{"timeStamp": stamp, "average": 1073741824}]}],
                    },
                ]
            },
        )
    if path.endswith("/start") or path.endswith("/stop"):
        return httpx.Response(202)
    # A container-app GET: report running unless it's the explicitly-stopped one.
    running = "Stopped" if "stopped-app" in path else "Running"
    return httpx.Response(200, json={"properties": {"runningStatus": running}})


def _provider(governed: tuple[str, ...] = ("lunaris-prod-api",)) -> AzureProdOpsProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_arm_handler))
    arm = ArmClient(
        client,
        identity_endpoint="https://identity.local/token",
        identity_header="hdr",
        client_id="cid",
    )
    return AzureProdOpsProvider(
        arm,
        subscription_id="sub-1",
        resource_group="rg-lunaris-prod",
        api_app="lunaris-prod-api",
        governed_apps=governed,
    )


async def test_cost_daily_parses_rows_and_flags_today_partial() -> None:
    series = await _provider().get_cost_daily(2)

    assert series.currency == "CAD"
    assert len(series.points) == 2
    by_day = {p.day: p for p in series.points}
    assert by_day[_YESTERDAY].amount == 3.5
    assert by_day[_YESTERDAY].partial is False
    assert by_day[_TODAY].amount == 1.0
    assert by_day[_TODAY].partial is True


async def test_compute_series_parses_metrics_into_usage_and_cost() -> None:
    series = await _provider().get_compute_series(1)

    hour = datetime(_TODAY.year, _TODAY.month, _TODAY.day, tzinfo=UTC)
    point = next(p for p in series.points if p.hour == hour)
    assert point.replicas == 1.0
    assert point.cpu_cores == 0.5  # 5e8 nanocores → 0.5 cores
    assert point.memory_gb == 1.0  # 1 GiB working set
    assert point.cost > 0  # amortized from the daily cost query


async def test_power_state_is_on_when_the_api_app_runs() -> None:
    state = await _provider(("lunaris-prod-api", "lunaris-prod-video-worker")).get_power_state()

    assert state.is_on is True
    assert {a.name for a in state.apps} == {"lunaris-prod-api", "lunaris-prod-video-worker"}
    assert all(a.running for a in state.apps)


async def test_set_power_off_issues_stop_and_reports_state() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(("/start", "/stop")):
            calls.append(request.url.path.rsplit("/", 1)[1])
        return _arm_handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    arm = ArmClient(
        client, identity_endpoint="https://identity.local/token", identity_header="h", client_id="c"
    )
    provider = AzureProdOpsProvider(
        arm,
        subscription_id="sub-1",
        resource_group="rg-lunaris-prod",
        api_app="lunaris-prod-api",
        governed_apps=("lunaris-prod-api", "lunaris-prod-video-worker"),
    )

    await provider.set_power(on=False)

    assert calls == ["stop", "stop"]  # a stop action per governed app


@pytest.mark.parametrize("on", [True, False])
async def test_set_power_uses_the_right_action(on: bool) -> None:
    actions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(("/start", "/stop")):
            actions.append(request.url.path.rsplit("/", 1)[1])
        return _arm_handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    arm = ArmClient(
        client, identity_endpoint="https://identity.local/token", identity_header="h", client_id="c"
    )
    provider = AzureProdOpsProvider(
        arm,
        subscription_id="sub-1",
        resource_group="rg-lunaris-prod",
        api_app="lunaris-prod-api",
        governed_apps=("lunaris-prod-api",),
    )

    await provider.set_power(on=on)

    assert actions == ["start" if on else "stop"]


async def test_cost_daily_handles_an_empty_cost_response() -> None:
    # A resource group with no spend yet (or before the first daily rollup) returns no rows; the
    # adapter must still yield a full zero-filled window, not blow up.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"properties": {"columns": [], "rows": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    arm = ArmClient(
        client, identity_endpoint="https://identity.local/t", identity_header="h", client_id="c"
    )
    provider = AzureProdOpsProvider(
        arm, subscription_id="s", resource_group="rg", api_app="a", governed_apps=("a",)
    )

    series = await provider.get_cost_daily(3)

    assert len(series.points) == 3
    assert all(point.amount == 0.0 for point in series.points)


async def test_arm_request_raises_on_an_error_response() -> None:
    # A failed ARM call must surface (so the endpoint errors honestly), never be swallowed.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(500, json={"error": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    arm = ArmClient(
        client, identity_endpoint="https://identity.local/t", identity_header="h", client_id="c"
    )
    provider = AzureProdOpsProvider(
        arm, subscription_id="s", resource_group="rg", api_app="a", governed_apps=("a",)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.get_cost_daily(7)
