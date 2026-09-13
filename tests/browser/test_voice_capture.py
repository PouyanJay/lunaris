"""Browser-generated microphone fixture traverses real worklet/WAV/API, without grading."""

import httpx
import pytest
from playwright.async_api import async_playwright, expect
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("servers", [{"app": "voice_app"}], indirect=True)
async def test_microphone_draft_and_cleanup(servers):  # noqa: F811
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.add_init_script("""(() => {
          window.micStreams = [];
          navigator.mediaDevices.getUserMedia = async () => {
            const context = new AudioContext();
            await context.resume();
            const oscillator = context.createOscillator();
            const destination = context.createMediaStreamDestination();
            oscillator.connect(destination);
            oscillator.start();
            const stream = destination.stream;
            const track = stream.getTracks()[0];
            const stop = track.stop.bind(track);
            track.stop = () => { stop(); oscillator.stop(); void context.close(); };
            window.micStreams.push(stream);
            return stream;
          };
        })();""")
        await page.goto(f"{web}/tests/voice-capture.html?api={api}")
        await expect(page.get_by_role("heading")).to_have_text("Microphone verification")
        assert await page.evaluate("window.micStreams.length") == 0
        session_id = await page.locator("main").get_attribute("data-session-id")
        async with httpx.AsyncClient(base_url=api) as client:
            before = (await client.get(f"/api/live/sessions/{session_id}")).json()
            await page.get_by_role("button", name="Speak", exact=True).click()
            await expect(page.get_by_role("status")).to_have_text("recording")
            await page.wait_for_timeout(350)
            async with page.expect_response(
                lambda r: "/voice/transcriptions?" in r.url
            ) as captured:
                await page.get_by_role("button", name="Finish recording").click()
            assert (await captured.value).status == 200
            await expect(page.get_by_role("textbox", name="Your answer")).to_have_value(
                "A fraction is a part of a whole."
            )
            assert await page.evaluate(
                "window.micStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))"
            )
            after = (await client.get(f"/api/live/sessions/{session_id}")).json()
            assert after == before
            await page.get_by_role("button", name="Speak", exact=True).click()
            await expect(page.get_by_role("status")).to_have_text("recording")
            await page.get_by_role("button", name="Cancel recording").click()
            await expect(page.get_by_role("status")).to_have_text("idle")
            assert await page.evaluate(
                "window.micStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))"
            )
        await browser.close()
