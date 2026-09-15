"""Preparation review remains readable and keyboard-operable across viewports and themes."""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect
from test_sim_roundtrip import servers  # noqa: F401

pytestmark = pytest.mark.browser


async def test_preparation_report_responsive_output_and_source_details(
    servers: tuple[str, str],  # noqa: F811
    tmp_path: Path,
) -> None:
    _, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{web}/tests/corpus-report.html")
            await expect(page.get_by_role("status")).to_have_text("Ready for review")
            await expect(page.get_by_text("Learn first: Electronic health records")).to_be_visible()
            await expect(page.get_by_text("Added: Electronic health records")).to_be_visible()
            await expect(
                page.get_by_text("Electronic health records: A usable video clip is not available.")
            ).to_be_visible()
            await expect(page.get_by_text("Who may access a patient record?")).to_be_visible()
            await expect(page.get_by_text("Fixture-only evidence")).to_have_count(0)
            details = page.locator("summary", has_text="Source details")
            await details.focus()
            await page.keyboard.press("Enter")
            await expect(page.get_by_text("verify-v1", exact=True)).to_be_visible()
            for width, theme in [(1280, "light"), (390, "dark")]:
                await page.set_viewport_size({"width": width, "height": 900})
                await page.evaluate(
                    "theme => document.documentElement.setAttribute('data-theme', theme)", theme
                )
                assert await page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                await page.screenshot(
                    path=str(tmp_path / f"corpus-report-{theme}.png"), full_page=True
                )
        finally:
            await browser.close()
