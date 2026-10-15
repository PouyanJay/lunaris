"""Contract tests for the real Azure ARM prod-ops adapter.

No live Azure: an ``httpx.MockTransport`` stands in for the managed-identity token endpoint and ARM,
so we verify the adapter issues the right requests (cost query, metrics, container-app run state,
start/stop actions) and parses the responses. The live behaviour is validated at deploy.
"""

import json
from datetime import UTC, date, datetime, timedelta, tzinfo

import httpx
import pytest
from lunaris_api.prod_ops import (
    ArmClient,
    AzureProdOpsProvider,
    GovernedResources,
    PowerStatus,
    ProdPowerActionError,
    ResourceKind,
)

# A fixed anchor day (mid-month, no boundary); the adapter's clock is frozen to it below so the
# cost/metrics date windows match the fake responses regardless of when the suite runs. Previously
# `_TODAY = now()` at import time diverged from the adapter's call-time `now()` when a run straddled
# UTC midnight — the assertions then looked up a stale day not in the series (KeyError).
_TODAY = date(2026, 1, 15)
_YESTERDAY = _TODAY - timedelta(days=1)


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the Azure adapter's ``datetime.now`` to the fixed anchor day, so its date math lines up
    with the fake responses' `_TODAY`/`_YESTERDAY` deterministically."""
    frozen = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 12, 0, tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr("lunaris_api.prod_ops.azure_provider.datetime", _FrozenDateTime)


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


def _provider(
    handler=_arm_handler,
    *,
    apps: tuple[str, ...] = ("lunaris-prod-api",),
    vms: tuple[str, ...] = (),
) -> AzureProdOpsProvider:
    """The real adapter over the real ``ArmClient``, with ``handler`` standing in for Azure."""
    arm = ArmClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        identity_endpoint="https://identity.local/token",
        identity_header="hdr",
        client_id="cid",
    )
    return AzureProdOpsProvider(
        arm,
        subscription_id="sub-1",
        resource_group="rg-lunaris-prod",
        api_app="lunaris-prod-api",
        governed=GovernedResources(container_apps=apps, virtual_machines=vms),
    )


async def test_cost_query_sends_an_actual_cost_daily_body() -> None:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Microsoft.CostManagement/query"):
            captured.append(json.loads(request.content))
        return _arm_handler(request)

    provider = _provider(handler)

    await provider.get_cost_daily(2)

    assert len(captured) == 1
    body = captured[0]
    assert body["type"] == "ActualCost"
    assert body["dataset"]["granularity"] == "Daily"


async def test_metrics_request_asks_for_the_usage_metrics_hourly() -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/microsoft.insights/metrics"):
            captured.append(request.url)
        return _arm_handler(request)

    provider = _provider(handler)

    await provider.get_compute_series(1)

    assert len(captured) == 1
    params = captured[0].params
    assert params["metricnames"] == "Replicas,UsageNanoCores,WorkingSetBytes"
    assert params["interval"] == "PT1H"
    # The timespan must use a 'Z' suffix, never '+00:00' — the '+' decodes to a space in a URL
    # query string and ARM rejects the interval (the bug that 400'd every compute load).
    timespan = params["timespan"]
    assert "+" not in timespan
    assert timespan.count("Z") == 2


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
    state = await _provider(
        apps=("lunaris-prod-api", "lunaris-prod-video-worker")
    ).get_power_state()

    assert state.is_on is True
    assert {r.name for r in state.resources} == {"lunaris-prod-api", "lunaris-prod-video-worker"}
    assert all(r.status is PowerStatus.RUNNING for r in state.resources)


async def test_set_power_off_issues_stop_and_reports_state() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(("/start", "/stop")):
            calls.append(request.url.path.rsplit("/", 1)[1])
        return _arm_handler(request)

    provider = _provider(handler, apps=("lunaris-prod-api", "lunaris-prod-video-worker"))

    await provider.set_power(on=False)

    assert calls == ["stop", "stop"]  # a stop action per governed app


@pytest.mark.parametrize("on", [True, False])
async def test_set_power_uses_the_right_action(on: bool) -> None:
    actions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(("/start", "/stop")):
            actions.append(request.url.path.rsplit("/", 1)[1])
        return _arm_handler(request)

    provider = _provider(handler)

    await provider.set_power(on=on)

    assert actions == ["start" if on else "stop"]


async def test_cost_daily_handles_an_empty_cost_response() -> None:
    # A resource group with no spend yet (or before the first daily rollup) returns no rows; the
    # adapter must still yield a full zero-filled window, not blow up.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"properties": {"columns": [], "rows": []}})

    provider = _provider(handler)

    series = await provider.get_cost_daily(3)

    assert len(series.points) == 3
    assert all(point.amount == 0.0 for point in series.points)


async def test_arm_request_raises_on_an_error_response() -> None:
    # A failed ARM call must surface (so the endpoint errors honestly), never be swallowed.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(500, json={"error": "boom"})

    provider = _provider(handler)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.get_cost_daily(7)


def _app_status_handler(statuses: dict[str, str | None]):
    """ARM double whose container-app GETs report ``statuses[name]`` as ``runningStatus`` (``None``
    omits the field)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        running_status = statuses[request.url.path.rsplit("/", 1)[1]]
        properties = {} if running_status is None else {"runningStatus": running_status}
        return httpx.Response(200, json={"properties": properties})

    return handler


@pytest.mark.parametrize(
    ("running_status", "expected", "settled"),
    [
        ("Running", PowerStatus.RUNNING, True),
        ("Stopped", PowerStatus.STOPPED, True),
        # An in-progress start/stop is neither up nor down yet.
        ("Progressing", PowerStatus.TRANSITIONING, False),
        # A state Azure reports that is neither must not keep a watcher polling forever.
        ("Failed", PowerStatus.UNKNOWN, True),
        (None, PowerStatus.UNKNOWN, True),
    ],
)
async def test_container_app_running_status_maps_to_a_power_status(
    running_status: str | None, expected: PowerStatus, settled: bool
) -> None:
    provider = _provider(_app_status_handler({"lunaris-prod-api": running_status}))

    state = await provider.get_power_state()

    assert [r.status for r in state.resources] == [expected]
    assert state.settled is settled


async def test_power_is_unsettled_while_any_resource_is_transitioning() -> None:
    provider = _provider(
        _app_status_handler({"lunaris-prod-api": "Running", "lunaris-prod-copilot": "Progressing"}),
        apps=("lunaris-prod-api", "lunaris-prod-copilot"),
    )

    state = await provider.get_power_state()

    assert state.is_on is True
    assert state.settled is False


def test_the_prod_default_governs_every_workload_but_never_the_control_plane() -> None:
    governed = GovernedResources.prod_default()

    assert set(governed.container_apps) == {
        "lunaris-prod-api",
        "lunaris-prod-video-worker",
        "lunaris-prod-inference",
        "lunaris-prod-embeddings",
        "lunaris-prod-cover-worker",
        "lunaris-prod-copilot",
    }
    assert "lunaris-prod-control" not in governed.container_apps


_VM = "lunaris-prod-sim-worker"


def _vm_handler(power_code: str, *, record: list[tuple[str, str]] | None = None, fail: str = ""):
    """ARM double: container apps report Running, the VM reports ``power_code`` from its instance
    view. POST actions are recorded as (resource, action); the one on ``fail`` answers 403."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        segments = request.url.path.split("/")
        if request.method == "POST":
            resource, action = segments[-2], segments[-1]
            if record is not None:
                record.append((resource, action))
            return httpx.Response(403 if resource == fail else 202)
        if "/virtualMachines/" in request.url.path:
            statuses = [{"code": "ProvisioningState/succeeded"}, {"code": power_code}]
            return httpx.Response(
                200, json={"properties": {"instanceView": {"statuses": statuses}}}
            )
        return httpx.Response(200, json={"properties": {"runningStatus": "Running"}})

    return handler


@pytest.mark.parametrize(
    ("power_code", "expected"),
    [
        ("PowerState/running", PowerStatus.RUNNING),
        ("PowerState/deallocated", PowerStatus.STOPPED),
        ("PowerState/deallocating", PowerStatus.TRANSITIONING),
        ("PowerState/starting", PowerStatus.TRANSITIONING),
    ],
)
async def test_vm_power_is_read_from_its_instance_view(
    power_code: str, expected: PowerStatus
) -> None:
    seen: list[httpx.Request] = []
    inner = _vm_handler(power_code)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return inner(request)

    provider = _provider(handler, apps=(), vms=(_VM,))

    state = await provider.get_power_state()

    assert [(r.name, r.kind, r.status) for r in state.resources] == [
        (_VM, ResourceKind.VIRTUAL_MACHINE, expected)
    ]
    vm_read = next(r for r in seen if "/virtualMachines/" in r.url.path)
    assert vm_read.url.path.endswith(f"/Microsoft.Compute/virtualMachines/{_VM}")
    assert vm_read.url.params["$expand"] == "instanceView"


async def test_power_off_stops_the_api_first_and_deallocates_the_vm_last() -> None:
    actions: list[tuple[str, str]] = []
    # The API is listed last on purpose: the stop order must come from the adapter, not the config.
    provider = _provider(
        _vm_handler("PowerState/running", record=actions),
        apps=("lunaris-prod-copilot", "lunaris-prod-api"),
        vms=(_VM,),
    )

    await provider.set_power(on=False)

    # Deallocate, never power off: a powered-off VM keeps billing for its compute.
    assert actions == [
        ("lunaris-prod-api", "stop"),
        ("lunaris-prod-copilot", "stop"),
        (_VM, "deallocate"),
    ]


async def test_power_on_starts_the_vm_first_and_the_api_last() -> None:
    actions: list[tuple[str, str]] = []
    provider = _provider(
        _vm_handler("PowerState/deallocated", record=actions),
        apps=("lunaris-prod-api", "lunaris-prod-copilot"),
        vms=(_VM,),
    )

    await provider.set_power(on=True)

    assert actions == [
        (_VM, "start"),
        ("lunaris-prod-copilot", "start"),
        ("lunaris-prod-api", "start"),
    ]


async def test_a_governed_resource_that_does_not_exist_is_skipped() -> None:
    # An environment deployed without the simulators has no VM; the switch must still work.
    actions: list[tuple[str, str]] = []
    inner = _vm_handler("PowerState/running", record=actions)

    def handler(request: httpx.Request) -> httpx.Response:
        if "/virtualMachines/" in request.url.path:
            if request.method == "POST":
                actions.append((_VM, request.url.path.rsplit("/", 1)[1]))
            return httpx.Response(404, json={"error": {"code": "ResourceNotFound"}})
        return inner(request)

    provider = _provider(handler, vms=(_VM,))

    state = await provider.get_power_state()
    await provider.set_power(on=False)

    assert [r.name for r in state.resources] == ["lunaris-prod-api"]
    assert actions == [("lunaris-prod-api", "stop"), (_VM, "deallocate")]


async def test_a_rejected_action_does_not_stop_the_rest_and_is_reported() -> None:
    actions: list[tuple[str, str]] = []
    # The API's stop is refused (e.g. a missing role); everything after it is still attempted.
    provider = _provider(
        _vm_handler("PowerState/running", record=actions, fail="lunaris-prod-api"),
        apps=("lunaris-prod-api", "lunaris-prod-copilot"),
        vms=(_VM,),
    )

    with pytest.raises(ProdPowerActionError) as raised:
        await provider.set_power(on=False)

    assert raised.value.failed == ("lunaris-prod-api",)
    assert actions == [
        ("lunaris-prod-api", "stop"),
        ("lunaris-prod-copilot", "stop"),
        (_VM, "deallocate"),
    ]


def test_the_prod_default_governs_the_simulator_vm() -> None:
    assert GovernedResources.prod_default().virtual_machines == (_VM,)
