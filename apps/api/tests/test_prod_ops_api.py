"""Prod-operations admin API — the walking skeleton (T0).

Hermetic (mirrors test_admin_users_api): HS256 tokens the API trusts, an admin allowlist, and an
in-memory prod-ops provider double. Exercises the real router → admin dependency → provider path;
the Azure ARM adapter is a thin wrapper verified separately. T0 proves only the admin-gated
round-trip for ``GET /api/admin/prod-ops/summary``; cost/compute/power behaviour lands later.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_prod_ops_provider
from lunaris_api.prod_ops import FakeProdOpsProvider, ProdOpsSummary

ADMIN_EMAIL = "owner@lunaris.test"
ADMIN_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_SUMMARY = ProdOpsSummary(resource_group="rg-lunaris-prod", currency="CAD")


def _build_client(tmp_path: Path, provider: FakeProdOpsProvider) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,
        admin_emails=(ADMIN_EMAIL,),
    )
    app.dependency_overrides[get_prod_ops_provider] = lambda: provider
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def provider() -> FakeProdOpsProvider:
    return FakeProdOpsProvider(summary=_SUMMARY)


@pytest.fixture
async def client(tmp_path: Path, provider: FakeProdOpsProvider) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, provider) as http_client:
        yield http_client


def _admin() -> dict[str, str]:
    return auth_headers(ADMIN_USER, email=ADMIN_EMAIL)


def _member() -> dict[str, str]:
    return auth_headers(MEMBER_USER, email="member@lunaris.test")


async def test_summary_returns_the_prod_ops_overview_for_an_admin(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/admin/prod-ops/summary", headers=_admin())

    assert response.status_code == 200
    assert response.json() == {"resourceGroup": "rg-lunaris-prod", "currency": "CAD"}


async def test_summary_carries_a_correlation_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/prod-ops/summary", headers=_admin())

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-Id"])


async def test_summary_without_a_token_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/prod-ops/summary")).status_code == 401


async def test_summary_for_a_non_admin_is_403(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/prod-ops/summary", headers=_member())

    assert response.status_code == 403


async def test_cost_defaults_to_seven_days_with_a_partial_latest_day(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/admin/prod-ops/cost", headers=_admin())

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "CAD"
    assert len(body["points"]) == 7
    # Oldest-first; only the most recent day is partial (cost data lags ~8-24h).
    assert [p["isPartial"] for p in body["points"]] == [False] * 6 + [True]
    assert body["points"][0]["day"] < body["points"][-1]["day"]


async def test_cost_honours_the_days_window(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/prod-ops/cost?days=3", headers=_admin())

    assert response.status_code == 200
    assert len(response.json()["points"]) == 3


async def test_cost_rejects_an_out_of_range_window(client: httpx.AsyncClient) -> None:
    assert (
        await client.get("/api/admin/prod-ops/cost?days=0", headers=_admin())
    ).status_code == 422
    assert (
        await client.get("/api/admin/prod-ops/cost?days=91", headers=_admin())
    ).status_code == 422


async def test_cost_for_a_non_admin_is_403(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/prod-ops/cost", headers=_member())).status_code == 403


async def test_compute_defaults_to_seven_days_hourly_with_usage_and_cost(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/admin/prod-ops/compute", headers=_admin())

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "CAD"
    assert len(body["points"]) == 7 * 24  # hourly over the window
    point = body["points"][0]
    # Each hour carries every usage dimension plus the amortized cost (dual-axis source).
    assert set(point) >= {"hour", "replicas", "cpuCores", "memoryGb", "cost"}


async def test_compute_honours_the_days_window(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/prod-ops/compute?days=2", headers=_admin())

    assert response.status_code == 200
    assert len(response.json()["points"]) == 2 * 24


async def test_compute_for_a_non_admin_is_403(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/prod-ops/compute", headers=_member())).status_code == 403


async def test_power_state_reports_on_and_each_governed_app(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/prod-ops/power", headers=_admin())

    assert response.status_code == 200
    body = response.json()
    assert body["isOn"] is True
    assert {app["name"] for app in body["apps"]} >= {"lunaris-prod-api"}
    assert all(app["running"] for app in body["apps"])


async def test_power_off_requires_confirmation(client: httpx.AsyncClient) -> None:
    # Without confirm, the self-DoS toggle is refused and nothing changes.
    response = await client.post(
        "/api/admin/prod-ops/power", json={"on": False, "confirm": False}, headers=_admin()
    )

    assert response.status_code == 400
    assert (await client.get("/api/admin/prod-ops/power", headers=_admin())).json()["isOn"] is True


async def test_power_off_then_on_flips_the_state(client: httpx.AsyncClient) -> None:
    off = await client.post(
        "/api/admin/prod-ops/power", json={"on": False, "confirm": True}, headers=_admin()
    )
    assert off.status_code == 200
    assert off.json()["isOn"] is False
    assert all(not app["running"] for app in off.json()["apps"])
    # The state persists for the next read, then comes back on.
    assert (await client.get("/api/admin/prod-ops/power", headers=_admin())).json()["isOn"] is False
    on = await client.post(
        "/api/admin/prod-ops/power", json={"on": True, "confirm": True}, headers=_admin()
    )
    assert on.json()["isOn"] is True


async def test_power_for_a_non_admin_is_403(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/prod-ops/power", headers=_member())).status_code == 403
    toggle = await client.post(
        "/api/admin/prod-ops/power", json={"on": False, "confirm": True}, headers=_member()
    )
    assert toggle.status_code == 403


@pytest.mark.parametrize(("endpoint", "days"), [("cost", 1), ("cost", 90), ("compute", 1)])
async def test_window_boundaries_are_accepted(
    client: httpx.AsyncClient, endpoint: str, days: int
) -> None:
    response = await client.get(f"/api/admin/prod-ops/{endpoint}?days={days}", headers=_admin())

    assert response.status_code == 200
    expected = days if endpoint == "cost" else days * 24
    assert len(response.json()["points"]) == expected


async def test_power_toggle_rejects_a_malformed_body(client: httpx.AsyncClient) -> None:
    # `on`/`confirm` are required booleans — a missing field is a 422, not a 500.
    response = await client.post("/api/admin/prod-ops/power", json={}, headers=_admin())

    assert response.status_code == 422
