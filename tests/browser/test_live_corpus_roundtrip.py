"""Real authenticated course preparation, review and bounded playback with durable state."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from lunaris_runtime.persistence import (
    SupabaseCourseStore,
    SupabaseRunStore,
    SupabaseVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import Course, RunStatus
from playwright.async_api import Route, async_playwright, expect
from test_sim_authenticated import login
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY") or not os.getenv("SUPABASE_DB_URL"),
        reason="local database and storage required",
    ),
]
ROOT = Path(__file__).resolve().parents[2]


def _course(course_id: str) -> Course:
    return Course.model_validate(
        {
            "id": course_id,
            "topic": "Consent for patient data",
            "status": "published",
            "modules": [
                {
                    "id": "privacy",
                    "title": "Consent",
                    "objectives": [
                        {
                            "statement": "Explain consent",
                            "bloomLevel": "understand",
                            "kc": "consent",
                            "assessedBy": ["q1"],
                        }
                    ],
                    "lessons": [
                        {
                            "id": "consent-lesson",
                            "segments": {
                                "activate": {"prose": "Recall consent."},
                                "demonstrate": {"prose": "Consent has a purpose."},
                                "apply": {"prose": "Explain the purpose of consent."},
                                "integrate": {"prose": "Use consent at work."},
                            },
                        }
                    ],
                    "assessment": {
                        "items": [
                            {
                                "id": "q1",
                                "prompt": "Explain consent.",
                                "objective": "Explain consent",
                                "answer": "PRIVATE ANSWER only in the source snapshot",
                                "passCriterion": "Explain consent's purpose.",
                            }
                        ]
                    },
                }
            ],
        }
    )


def _state(database: psycopg.Connection, graph_id: str) -> tuple:
    graph = database.execute(
        "select payload from public.live_graphs where id=%s", (graph_id,)
    ).fetchone()
    session = database.execute(
        "select payload from public.live_sessions where graph_id=%s order by id", (graph_id,)
    ).fetchall()
    knowledge = database.execute(
        "select to_jsonb(k) from public.live_knowledge k where graph_id=%s order by node_id",
        (graph_id,),
    ).fetchall()
    return graph, session, knowledge


async def _https_storage_bridge(route: Route) -> None:
    response = await route.fetch(url=route.request.url.replace("https://", "http://", 1))
    await route.fulfill(response=response)


@pytest.mark.parametrize("servers", [{"app": "live_corpus_app", "auth": True}], indirect=True)
@pytest.mark.parametrize("source_change", ["edit", "delete"])
async def test_real_course_to_live_clip_and_fresh_source_guard(
    servers: tuple[str, str],  # noqa: F811
    tmp_path: Path,
    source_change: str,
) -> None:
    api, web = servers
    options = {"url_env": "LOCAL_SUPABASE_URL", "service_key_env": "LOCAL_SUPABASE_SERVICE_KEY"}
    courses, storage = SupabaseCourseStore(**options), SupabaseVideoStorage(**options)
    course_id = f"browser-course-{uuid4().hex}"
    owner = None
    media_path = None
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as database:
            try:
                page = await login(browser)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                await page.goto(f"{web}/tests/corpus-report.html")
                owner = await page.evaluate(
                    "JSON.parse(localStorage.getItem('sb-identity-auth-token')).user.id"
                )
                database.execute("insert into auth.users(id) values (%s)", (owner,))
                courses.save(_course(course_id), owner_id=owner)
                runs = SupabaseRunStore(**options)
                await runs.start(
                    run_id=uuid4().hex,
                    course_id=course_id,
                    topic="Consent for patient data",
                    owner_id=owner,
                )
                await runs.finish(
                    course_id=course_id,
                    status=RunStatus.COMPLETED,
                    kc_count=1,
                    module_count=1,
                    owner_id=owner,
                )
                media_path = VideoArtifactPaths.for_coordinates(
                    owner, course_id, "browser-clip"
                ).mp4
                await storage.upload(
                    path=media_path,
                    data=(ROOT / "packages/video/src/lunaris_video/assets/stub.mp4").read_bytes(),
                    content_type="video/mp4",
                )
                storage_origin = os.environ["LOCAL_SUPABASE_URL"].replace("http://", "https://", 1)
                await page.route(f"{storage_origin}/storage/**", _https_storage_bridge)
                await page.goto(f"{web}/tests/live-corpus.html?api={api}&source=course")
                await expect(
                    page.get_by_role("button", name=re.compile("Source course"))
                ).to_be_visible()
                assert not errors, errors
                await page.get_by_role("button", name=re.compile("Source course")).click()
                await page.get_by_role(
                    "option", name="Consent for patient data", exact=True
                ).click()
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
                graph_id = graph["graphId"]
                assert graph["corpus"]["status"] == "verified"
                assert graph["corpus"]["runId"] == response.headers["x-run-id"]
                assert "PRIVATE ANSWER" not in json.dumps(graph)
                assert "token=" not in json.dumps(graph)
                await expect(page.get_by_role("status")).to_have_text("Ready for review")
                await expect(page.get_by_text("Consent in context", exact=True)).to_be_visible()
                assert _state(database, graph_id)[1] == []
                await page.locator("main").evaluate("element => { element.scrollTop = 0; }")
                await page.screenshot(path=str(tmp_path / "live-corpus-review.png"))
                snapshot = database.execute(
                    "select count(*) from public.live_corpus_snapshots "
                    "where owner_id=%s and course_id=%s",
                    (owner, course_id),
                ).fetchone()
                assert snapshot == (1,)
                async with page.expect_response(
                    lambda response: (
                        response.url == f"{api}/api/live/sessions"
                        and response.request.method == "POST"
                    )
                ) as started:
                    await page.get_by_role("button", name="Start a session", exact=True).click()
                session_response = await started.value
                assert session_response.status == 201
                session = await session_response.json()
                assert session["turns"][-1]["materials"]
                assert "PRIVATE ANSWER" not in json.dumps(session)
                before = _state(database, graph_id)
                await expect(
                    page.get_by_role("button", name="Load clip", exact=True)
                ).to_be_visible()
                video = page.locator("video")
                assert await video.evaluate("v => v.paused && !v.hasAttribute('src')")
                await page.get_by_role("button", name="Load clip", exact=True).click()
                await expect(
                    page.get_by_role("button", name="Play clip", exact=True)
                ).to_be_visible()
                await page.get_by_role("button", name="Play clip", exact=True).click()
                await page.wait_for_function("document.querySelector('video').currentTime > 0.65")
                await page.wait_for_function("document.querySelector('video').paused")
                assert await video.evaluate("v => Math.abs(v.currentTime - 1.4) < 0.01")
                assert _state(database, graph_id) == before
                assert errors == []
                await page.locator("main").evaluate("element => { element.scrollTop = 0; }")
                await page.screenshot(path=str(tmp_path / "live-corpus-session.png"))
                if source_change == "edit":
                    changed = _course(course_id)
                    changed.modules[0].lessons[0].segments.activate.prose = "The source was edited."
                    courses.save(changed, owner_id=owner)
                else:
                    database.execute(
                        "delete from public.courses where id=%s and user_id=%s", (course_id, owner)
                    )
                async with page.expect_response(
                    lambda response: response.url == f"{api}/api/live/graphs/{graph_id}"
                ) as reloaded:
                    await page.goto(f"{web}/tests/live-corpus.html?api={api}&graph={graph_id}")
                assert (await reloaded.value).status in {404, 409}
                await expect(page.get_by_role("alert")).to_be_visible()
                await expect(page.get_by_text("Consent in context", exact=True)).to_have_count(0)
                await expect(
                    page.get_by_role("button", name="Start a session", exact=True)
                ).to_have_count(0)
            finally:
                try:
                    await browser.close()
                finally:
                    try:
                        if media_path is not None:
                            await storage.delete(paths=[media_path])
                    finally:
                        if owner is not None:
                            database.execute("delete from auth.users where id=%s", (owner,))
