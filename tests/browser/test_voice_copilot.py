"""Real Copilot browser/runtime/API path retains one confirmed voice answer."""

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from _voice_microphone import install_microphone
from playwright.async_api import async_playwright, expect
from test_sim_authenticated import login
from test_sim_roundtrip import ROOT, _port, servers  # noqa: F401

pytestmark = pytest.mark.browser


@pytest.fixture
def copilot(servers: tuple[str, str], tmp_path: Path) -> Iterator[str]:  # noqa: F811
    api, web = servers
    port = _port()
    env = {
        **os.environ,
        "LUNARIS_API_URL": api,
        "LUNARIS_COPILOT_ORIGINS": web,
        "PORT": str(port),
        "LUNARIS_LIVE_SIMS": "stub",
    }
    with (tmp_path / "copilot.log").open("w") as log:
        process = subprocess.Popen(
            ["node_modules/.bin/tsx", "src/main.ts"],
            cwd=ROOT / "apps/copilot",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            with httpx.Client(timeout=0.5) as client:
                while True:
                    assert process.poll() is None, "Copilot exited before readiness"
                    assert time.monotonic() < deadline, "Copilot did not start"
                    try:
                        if client.get(f"http://127.0.0.1:{port}/healthz").is_success:
                            break
                    except httpx.TransportError:
                        pass
                    # Poll readiness; this delay does not stand in for a behavior assertion.
                    time.sleep(0.05)
            yield f"http://127.0.0.1:{port}"
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize(
    "servers", [{"app": "voice_session_app", "auth": True, "practice": True}], indirect=True
)
async def test_copilot_voice_uses_real_composer_bridge(
    servers: tuple[str, str],  # noqa: F811
    copilot: str,
    tmp_path: Path,
) -> None:
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await login(browser)
        await install_microphone(page)
        async with page.expect_response(
            lambda r: r.url.endswith("/api/live/sessions") and r.request.method == "POST"
        ) as opened:
            await page.goto(f"{web}/tests/voice-session.html?api={api}&copilot={copilot}")
        session = await (await opened.value).json()
        sid = session["sessionId"]
        voice = page.get_by_role("region", name="Voice controls")
        await expect(voice.get_by_role("button", name="Speak", exact=True)).to_be_enabled()
        await voice.get_by_role("button", name="Speak", exact=True).click()
        await expect(voice.get_by_role("button", name="Finish recording")).to_be_visible()
        await page.wait_for_function("window.micContexts.at(-1).currentTime >= 0.25")
        await voice.get_by_role("button", name="Finish recording").click()
        draft = page.get_by_role("textbox", name="Your answer").last
        await expect(draft).to_have_value("A fraction is a part of a whole.")
        await draft.fill("Explain proportional scaling: when x doubles, y doubles.")
        token = await page.evaluate(
            "JSON.parse(localStorage.getItem('sb-identity-auth-token')).access_token"
        )
        async with httpx.AsyncClient(
            base_url=api, headers={"Authorization": f"Bearer {token}"}
        ) as client:
            before = (await client.get(f"/api/live/sessions/{sid}")).json()
            assert before["turns"][0]["answer"] is None
            async with page.expect_response(
                lambda r: r.url.endswith("/agent/live/run") and r.request.method == "POST"
            ) as answered:
                await page.get_by_role("button", name="Send", exact=True).click()
            assert (await answered.value).status == 200
            await expect(voice.get_by_role("button", name="Speak", exact=True)).to_be_enabled()
            after = (await client.get(f"/api/live/sessions/{sid}")).json()
            assert len(after["turns"]) == len(before["turns"]) + 1
            assert after["turns"][0]["answer"] == (
                "Explain proportional scaling: when x doubles, y doubles."
            )
            assert len((await client.get("/test/voice-calls")).json()["transcriptions"]) == 1
            # After AG-UI surfaces arrive, the panel may also expose a card answer box.
            # Dictation must still enter only the ordinary composer, never every card.
            await expect(page.get_by_role("textbox", name="Your answer")).to_have_count(2)
            await voice.get_by_role("button", name="Speak", exact=True).click()
            await expect(voice.get_by_role("button", name="Finish recording")).to_be_visible()
            await page.wait_for_function("window.micContexts.at(-1).currentTime >= 0.25")
            await voice.get_by_role("button", name="Finish recording").click()
            await expect(draft).to_have_value("A fraction is a part of a whole.")
            values = await page.get_by_role("textbox", name="Your answer").evaluate_all(
                "boxes => boxes.map(box => box.value)"
            )
            assert values.count("A fraction is a part of a whole.") == 1
            assert (await client.get(f"/api/live/sessions/{sid}")).json() == after
            await voice.scroll_into_view_if_needed()
        await page.screenshot(path=str(tmp_path / "voice-copilot.png"), full_page=False)
        await browser.close()
