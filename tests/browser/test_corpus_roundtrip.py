"""Authenticated Chromium corpus preparation persists source provenance in Postgres."""

import json
import os
import re
from pathlib import Path

import httpx
import psycopg
import pytest
from playwright.async_api import async_playwright, expect
from test_sim_authenticated import login
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY") or not os.getenv("SUPABASE_DB_URL"),
        reason="local database is not configured",
    ),
]


@pytest.mark.parametrize("servers", [{"app": "corpus_app", "auth": True}], indirect=True)
async def test_owned_course_preparation_persists_source_and_reload(
    servers: tuple[str, str],  # noqa: F811
    tmp_path: Path,
) -> None:
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        owner = None
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as database:
            try:
                page = await login(browser)
                await page.goto(f"{web}/tests/corpus.html?api={api}")
                identity = await page.evaluate(
                    "JSON.parse(localStorage.getItem('sb-identity-auth-token'))"
                )
                owner = identity["user"]["id"]
                database.execute("insert into auth.users(id) values (%s)", (owner,))
                database.execute(
                    "insert into public.courses(id, user_id, status, payload) "
                    "values (%s,%s,%s,%s::jsonb)",
                    (
                        f"corpus-fixture-{owner}",
                        owner,
                        "published",
                        json.dumps(
                            {
                                "id": f"corpus-fixture-{owner}",
                                "topic": "Fixture course",
                                "status": "published",
                            }
                        ),
                    ),
                )
                await page.get_by_role("button", name=re.compile("Source course")).click()
                await page.get_by_role("option", name="Fixture course", exact=True).click()
                async with page.expect_response(
                    lambda response: (
                        response.url == f"{api}/api/live/graphs"
                        and response.request.method == "POST"
                    )
                ) as prepared:
                    await page.get_by_role("button", name="Prepare course", exact=True).click()
                response = await prepared.value
                assert response.status == 201
                graph = await response.json()
                source = graph["corpus"]
                assert source["courseId"] == "corpus-fixture"
                assert source["title"] == "Fixture course"
                assert source["digest"] == "a" * 64
                assert source["adapterVersion"] == "studio-v1"
                assert source["runId"] == response.headers["x-run-id"]
                assert source["status"] == "pending"
                graph_id = graph["graphId"]
                row = database.execute(
                    "select user_id::text, payload from public.live_graphs where id=%s",
                    (graph_id,),
                ).fetchone()
                assert row is not None
                assert row[0] == owner
                assert row[1]["corpus"] == source
                await expect(page.locator("main")).to_have_attribute("data-graph-id", graph_id)
                await expect(page.get_by_role("status")).to_have_text("Awaiting verification")
                async with page.expect_response(
                    lambda fetched: fetched.url == f"{api}/api/live/graphs/{graph_id}"
                ) as reloaded:
                    await page.get_by_role("button", name="Reload source", exact=True).click()
                assert (await (await reloaded.value).json())["corpus"] == source
                await expect(page.get_by_text("Fixture course", exact=True).last).to_be_visible()
                async with httpx.AsyncClient(base_url=api) as client:
                    anonymous = await client.get(f"/api/live/graphs/{graph_id}")
                assert anonymous.status_code == 401
                await page.screenshot(path=str(tmp_path / "corpus-roundtrip.png"), full_page=True)
            finally:
                await browser.close()
                if owner is not None:
                    database.execute("delete from public.live_graphs where user_id=%s", (owner,))
                    database.execute(
                        "delete from public.courses where id=%s and user_id=%s",
                        (f"corpus-fixture-{owner}", owner),
                    )
                    database.execute("delete from auth.users where id=%s", (owner,))
