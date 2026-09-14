"""Chromium speech transport traverses the real session loop without implicit answers."""

import httpx
import pytest
from playwright.async_api import async_playwright, expect
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("servers", [{"app": "voice_app"}], indirect=True)
async def test_transcript_edit_one_answer_and_streamed_tutor_speech(servers, tmp_path):  # noqa: F811
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"{web}/tests/voice.html?api={api}")
        await expect(page.get_by_role("heading", name="Voice roundtrip")).to_be_visible()
        session_id = await page.locator("main").get_attribute("data-session-id")
        async with httpx.AsyncClient(base_url=api) as client:
            before = (await client.get(f"/api/live/sessions/{session_id}")).json()
            async with page.expect_response(
                lambda r: "/voice/transcriptions?" in r.url
            ) as captured:
                await page.get_by_role("button", name="Transcribe fixture recording").click()
            transcription = await captured.value
            transcript = await transcription.json()
            assert transcription.status == 200
            assert transcription.headers["x-session-id"] == session_id
            assert transcription.headers["x-request-id"]
            assert transcript["source"] == {
                "turnSeq": before["turns"][-1]["seq"],
                "runId": before["turns"][-1]["runId"],
                "exchangeSequence": None,
            }
            assert transcript["provider"] == "browser-fixture"
            assert transcript["model"] == "fixture-v1"
            draft = page.get_by_role("textbox", name="Your answer")
            await expect(draft).to_have_value("A fraction is a part of a whole.")
            unchanged = (await client.get(f"/api/live/sessions/{session_id}")).json()
            assert unchanged == before
            edited = "A fraction describes equal parts of a whole, such as one of two halves."
            await draft.fill(edited)
            async with page.expect_response(lambda r: r.url.endswith("/turns")) as submitted:
                await page.get_by_role("button", name="Send", exact=True).click()
            assert (await submitted.value).status == 200
            await expect(page.get_by_text(edited, exact=True)).to_be_visible()
            persisted = (await client.get(f"/api/live/sessions/{session_id}")).json()
            assert len(persisted["turns"]) == len(before["turns"]) + 1
            assert persisted["turns"][0]["answer"] == edited
            async with page.expect_response(lambda r: r.url.endswith("/voice/speech")) as spoken:
                await page.get_by_role("button", name="Read tutor response").click()
            speech = await spoken.value
            assert speech.status == 200
            assert speech.headers["x-session-id"] == session_id
            assert speech.headers["x-request-id"]
            assert speech.headers["x-audio-sample-rate"] == "24000"
            # Assert the bytes consumed and played by the page. Chromium may discard its
            # separate CDP response-body copy for streamed audio before a debugger reads it.
            await expect(page.get_by_role("status")).to_have_text("Played 2400 samples")
            await expect(page.get_by_role("alert")).to_have_count(0)
            await expect(page.locator("main")).to_have_attribute("data-audio-running", "true")
            await expect(
                page.get_by_text(persisted["turns"][-1]["tutor"], exact=True)
            ).to_be_visible()
            after_speech = (await client.get(f"/api/live/sessions/{session_id}")).json()
            assert after_speech == persisted
            calls = (await client.get("/test/provider-calls")).json()
            assert calls["transcriptions"] == [{"run_id": transcription.headers["x-request-id"]}]
            assert speech.request.post_data_json["source"] == {
                "turnSeq": persisted["turns"][-1]["seq"],
                "runId": persisted["turns"][-1]["runId"],
            }
            assert calls["speech"] == [
                {"text": persisted["turns"][-1]["tutor"], "run_id": speech.headers["x-request-id"]}
            ]
        await page.screenshot(path=str(tmp_path / "voice-roundtrip.png"), full_page=True)
        await browser.close()
