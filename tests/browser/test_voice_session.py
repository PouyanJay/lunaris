"""Actual session controls keep voice, simulator state and assessment sequencing aligned."""

import httpx
import pytest
from _voice_microphone import install_microphone
from playwright.async_api import async_playwright, expect
from test_sim_authenticated import login
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser


@pytest.mark.parametrize(
    "servers", [{"app": "voice_session_app", "auth": True, "practice": True}], indirect=True
)
async def test_voice_session_and_simulator_reaction(servers, tmp_path):  # noqa: F811
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await login(browser)
        await install_microphone(page)
        async with page.expect_response(
            lambda r: r.url.endswith("/api/live/sessions") and r.request.method == "POST"
        ) as opened:
            await page.goto(f"{web}/tests/voice-session.html?api={api}")
        session = await (await opened.value).json()
        sid = session["sessionId"]
        token = await page.evaluate(
            "JSON.parse(localStorage.getItem('sb-identity-auth-token')).access_token"
        )
        voice = page.get_by_role("region", name="Voice controls")
        await expect(voice.get_by_role("button", name="Speak", exact=True)).to_be_enabled()
        async with page.expect_response(lambda r: r.url.endswith("/voice/speech")) as spoken:
            await voice.get_by_role("button", name="Read aloud", exact=True).click()
        assert (await spoken.value).status == 200
        frame = page.frame_locator("iframe").frame_locator("iframe")
        slider = frame.get_by_label("x value", exact=True)
        await expect(slider).to_have_value("5")
        await slider.focus()
        await slider.press("ArrowLeft")
        async with page.expect_response(lambda r: r.url.endswith("/sim")) as reacted:
            await frame.get_by_role("button", name="Discuss this state").click()
        reaction = await (await reacted.value).json()
        await expect(slider).to_have_value("0")
        await expect(voice.get_by_role("button", name="Read reaction")).to_be_enabled()
        async with page.expect_response(
            lambda r: r.url.endswith("/voice/speech")
        ) as reaction_audio:
            await voice.get_by_role("button", name="Read reaction").click()
        speech = await reaction_audio.value
        assert speech.status == 200
        assert (
            speech.request.post_data_json["source"]["exchangeSequence"]
            == reaction["event"]["sequence"]
        )
        async with httpx.AsyncClient(
            base_url=api, headers={"Authorization": f"Bearer {token}"}
        ) as client:
            before = (await client.get(f"/api/live/sessions/{sid}")).json()
            assert before["turns"][0]["answer"] is None
            await voice.get_by_role("button", name="Speak", exact=True).click()
            await expect(voice.get_by_role("button", name="Finish recording")).to_be_visible()
            await page.wait_for_function("window.micContexts.at(-1).currentTime >= 0.25")
            await voice.get_by_role("button", name="Finish recording").click()
            draft = page.get_by_role("textbox", name="Your answer")
            await expect(draft).to_have_value("A fraction is a part of a whole.")
            assert (await client.get(f"/api/live/sessions/{sid}")).json() == before
            await draft.fill(
                "Explain proportional scaling: when x doubles, y doubles because y is twice x."
            )
            await page.screenshot(path=str(tmp_path / "voice-session-preview.png"), full_page=True)
            async with page.expect_response(lambda r: r.url.endswith("/turns")) as answered:
                await page.get_by_role("button", name="Send", exact=True).click()
            assert (await answered.value).status == 200
            after = (await client.get(f"/api/live/sessions/{sid}")).json()
            assert len(after["turns"]) == len(before["turns"]) + 1
            assert (
                after["turns"][0]["answer"]
                == "Explain proportional scaling: when x doubles, y doubles because y is twice x."
            )
            calls = (await client.get("/test/voice-calls")).json()
            assert len(calls["transcriptions"]) == 1
            assert calls["speech"][-1]["text"] == reaction["reaction"]["text"]
            for _ in range(6):
                if after["status"] == "closed":
                    break
                await expect(voice.get_by_role("button", name="Speak", exact=True)).to_be_enabled()
                await voice.get_by_role("button", name="Speak", exact=True).click()
                await expect(voice.get_by_role("button", name="Finish recording")).to_be_visible()
                await page.wait_for_function("window.micContexts.at(-1).currentTime >= 0.25")
                await voice.get_by_role("button", name="Finish recording").click()
                await expect(draft).to_have_value("A fraction is a part of a whole.")
                await draft.fill(
                    "Explain proportional scaling: when x doubles, y doubles because y is twice x."
                )
                async with page.expect_response(lambda r: r.url.endswith("/turns")) as next_answer:
                    await page.get_by_role("button", name="Send", exact=True).click()
                assert (await next_answer.value).status == 200
                after = (await client.get(f"/api/live/sessions/{sid}")).json()
            assert after["status"] == "closed"
            await expect(voice.get_by_role("button", name="Speak", exact=True)).to_have_count(0)
            await expect(voice.get_by_role("button", name="Read aloud", exact=True)).to_be_enabled()
            async with page.expect_response(lambda r: r.url.endswith("/voice/speech")) as goodbye:
                await voice.get_by_role("button", name="Read aloud", exact=True).click()
            assert (await goodbye.value).status == 200
            assert (await client.get(f"/api/live/sessions/{sid}")).json() == after
        assert await page.evaluate(
            "window.micStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))"
        )
        await browser.close()
