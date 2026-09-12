"""Authenticated approved simulators preserve independent learner state and prevent escape."""

import asyncio
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from playwright.async_api import async_playwright, expect
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser
JWT_SECRET = "browser-fixture-signing-key-with-at-least-sixty-four-bytes-for-tests-only"


async def login(browser):
    owner = str(uuid4())
    now = int(time.time())
    token = jwt.encode(
        {"sub": owner, "aud": "authenticated", "iat": now, "exp": now + 3600},
        JWT_SECRET,
        algorithm="HS256",
    )
    page = await browser.new_page()
    import json

    stored = json.dumps(
        {
            "access_token": token,
            "refresh_token": "test-refresh",
            "token_type": "bearer",
            "expires_at": now + 3600,
            "expires_in": 3600,
            "user": {
                "id": owner,
                "aud": "authenticated",
                "role": "authenticated",
                "email": "test@example.test",
            },
        }
    )
    await page.add_init_script(
        "localStorage.setItem('sb-identity-auth-token', " + json.dumps(stored) + ");"
    )
    return page


@pytest.mark.parametrize("servers", [{"app": "approved_sim_app", "auth": True}], indirect=True)
async def test_authenticated_mount_replay_fresh_learner_and_revocation(servers, tmp_path):  # noqa: F811
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        first = await login(browser)
        await first.goto(f"{web}/tests/sim.html?api={api}")
        frame = first.frame_locator("iframe").frame_locator("iframe")
        slider = frame.get_by_label("x value", exact=True)
        await expect(slider).to_have_value("5")
        assert await first.locator("iframe").get_attribute("src") is None
        assert "connect-src 'none'" in await first.locator("iframe").get_attribute("srcdoc")
        await slider.focus()
        await slider.press("ArrowLeft")
        await expect(slider).to_have_value("4")
        await frame.get_by_role("button", name="Discuss this state").click()
        await expect(slider).to_have_value("0")
        await first.reload()
        await expect(
            first.frame_locator("iframe")
            .frame_locator("iframe")
            .get_by_label("x value", exact=True)
        ).to_have_value("0")
        second = await login(browser)
        await second.goto(f"{web}/tests/sim.html?api={api}")
        await expect(
            second.frame_locator("iframe")
            .frame_locator("iframe")
            .get_by_label("x value", exact=True)
        ).to_have_value("5")
        await first.screenshot(path=str(tmp_path / "approved-authenticated-simulator.png"))
        observed = asyncio.Event()
        escaped = []

        async def intercept(route):
            escaped.append(route.request.url)
            observed.set()
            await route.abort()

        first.on("console", lambda message: observed.set() if "frame-src" in message.text else None)
        await first.route("https://example.invalid/**", intercept)
        await (
            first.frame_locator("iframe")
            .frame_locator("iframe")
            .get_by_label("x value", exact=True)
            .evaluate("() => { location.href='https://example.invalid/?state=4'; }")
        )
        await asyncio.wait_for(observed.wait(), timeout=3)
        assert escaped == [], "Generated code escaped through its own frame navigation"
        async with httpx.AsyncClient() as client:
            await client.post(f"{api}/test/revoke")
        await first.reload()
        await expect(
            first.get_by_text("The simulator could not load. Continue with your explanation.")
        ).to_be_visible()
        assert await first.locator("iframe").count() == 0
        await browser.close()
