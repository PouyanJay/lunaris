"""Actual Chromium playback enforces a verified excerpt without learning mutations."""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[2]


async def test_clip_playback_bounds_keyboard_interruption_and_cleanup(
    servers: tuple[str, str],  # noqa: F811
    tmp_path: Path,
) -> None:
    _, web = servers
    media = (ROOT / "packages/video/src/lunaris_video/assets/stub.mp4").read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            mutations = []
            page.on(
                "request",
                lambda request: (
                    mutations.append(request.url) if request.method not in {"GET", "HEAD"} else None
                ),
            )
            await page.route(
                "**/test-fixture.mp4",
                lambda route: route.fulfill(
                    status=206,
                    headers={
                        "Content-Range": f"bytes 0-{len(media) - 1}/{len(media)}",
                        "Accept-Ranges": "bytes",
                    },
                    content_type="video/mp4",
                    body=media,
                ),
            )
            await page.goto(f"{web}/tests/corpus-clip.html")
            video = page.locator("video")
            assert await video.evaluate("v => v.paused && !v.hasAttribute('src')")
            await page.get_by_role("button", name="Load clip").focus()
            await page.keyboard.press("Enter")
            await expect(page.get_by_role("button", name="Play clip")).to_be_visible()
            await page.wait_for_function(
                "document.querySelector('video').paused && "
                "document.querySelector('video').currentTime >= 0.5"
            )
            await expect(page.get_by_role("button", name="Play clip")).to_be_focused()
            await page.keyboard.press("Enter")
            await page.wait_for_function("document.querySelector('video').currentTime > 0.65")
            await page.wait_for_function("document.querySelector('video').paused")
            assert await video.evaluate("v => Math.abs(v.currentTime - 1.4) < 0.01")
            await expect(page.get_by_label("Playback starts")).to_have_text("1")
            seek = page.get_by_role("slider", name="Seek clip")
            await seek.focus()
            await page.keyboard.press("Home")
            await page.wait_for_function("document.querySelector('video').currentTime === 0.5")
            await video.evaluate("v => { v.currentTime = 0; }")
            await page.wait_for_function("document.querySelector('video').currentTime === 0.5")
            await page.get_by_role("button", name="Play clip").click()
            await page.wait_for_function("!document.querySelector('video').paused")
            await page.get_by_role("button", name="Interrupt with voice").click()
            assert await video.evaluate("v => v.paused")
            await page.get_by_text("Transcript", exact=True).click()
            await expect(page.get_by_text("This is a bounded excerpt.")).to_be_visible()
            await page.screenshot(path=str(tmp_path / "corpus-clip.png"), full_page=True)
            await video.evaluate("v => { window.previousClip = v; }")
            await page.get_by_role("button", name="Next turn").click()
            assert await page.evaluate("previousClip.paused && !previousClip.hasAttribute('src')")
            assert await video.evaluate("v => v.paused && !v.hasAttribute('src')")
            await page.get_by_role("button", name="Close surface").click()
            await expect(video).to_have_count(0)
            assert mutations == []
        finally:
            await browser.close()
