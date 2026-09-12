"""Trusted browser driver. Candidate code stays in an opaque iframe inside Chromium's sandbox."""

import asyncio
import json
import sys

from playwright.async_api import Page, Route, async_playwright, expect

_HOST = "https://verifier.invalid/"
_APP = "https://candidate.invalid/"
_HOST_HTML = """<!doctype html><iframe sandbox="allow-scripts" src="https://candidate.invalid/"></iframe>
<script>
window.events = [];
addEventListener('message', e => {
  if(e.source === document.querySelector('iframe').contentWindow && window.events.length < 50)
    window.events.push(e.data);
});
</script>"""


class _Verification:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.reasons: list[str] = []
        self.passed = 0

    def reject(self, reason: str) -> None:
        if len(self.reasons) < 20:
            self.reasons.append(reason[:300])

    async def route(self, route: Route) -> None:
        if route.request.url == _HOST:
            await route.fulfill(content_type="text/html", body=_HOST_HTML)
        elif route.request.url == _APP and route.request.resource_type == "document":
            await route.fulfill(
                content_type="text/html",
                body=self.payload["html"],
                headers={"Content-Security-Policy": self.payload["csp"]},
            )
        else:
            self.reject("Attempted forbidden network request.")
            await route.abort()

    async def check_case(self, page: Page, case: dict) -> None:
        frame = page.frame_locator("iframe")
        for key, value in case["state"].items():
            control = frame.locator(f'[data-sim-param="{key}"]')
            await expect(control).to_be_visible()
            await control.fill(str(int(value)) if float(value).is_integer() else str(value))
            await control.press("Tab")
        await self.outputs(page, case["outputs"])
        await frame.locator('[data-sim-action="discuss"]').click()
        await page.wait_for_function(
            "state => window.events.some(e => e.type === 'lunaris.sim.event' && "
            "e.version === 1 && e.instanceId === 'verify-instance' && e.appId === 'verify-app' && "
            "['param_changed', 'milestone_reached', 'misconception_signal'].includes(e.kind) && "
            "e.state && Object.keys(e.state).length === Object.keys(state).length && "
            "Object.keys(state).every(k => e.state?.[k] === state[k]))",
            arg=case["state"],
        )
        await page.evaluate("window.events = []")

    async def outputs(self, page: Page, outputs: dict) -> None:
        for key, expected in outputs.items():
            output = page.frame_locator("iframe").locator(f'[data-sim-output="{key}"]')
            await expect(output).to_be_visible()
            await expect(output).to_have_text(expected)
            self.passed += 1

    async def command(
        self, page: Page, state: dict, *, message_type: str = "lunaris.sim.command"
    ) -> None:
        await page.evaluate(
            "message => document.querySelector('iframe').contentWindow.postMessage(message, '*')",
            {
                "type": message_type,
                "version": 1,
                "instanceId": "verify-instance",
                "appId": "verify-app",
                "active": True,
                "state": state,
            },
        )
        for key, value in state.items():
            await expect(
                page.frame_locator("iframe").locator(f'[data-sim-param="{key}"]')
            ).to_have_value(str(int(value)) if float(value).is_integer() else str(value))

    async def exercise(self, page: Page) -> None:
        await page.goto(_HOST)
        await page.wait_for_function(
            "window.events.some(e => e.type === 'lunaris.sim.ready' && e.version === 1)"
        )
        defaults = {
            key: p["default"] for key, p in self.payload["spec"]["contract"]["parameters"].items()
        }
        await self.command(page, defaults, message_type="lunaris.sim.init")
        for case in self.payload["spec"]["cases"]:
            await self.check_case(page, case)
        demonstration = self.payload["spec"]["cases"][0]
        await self.command(page, demonstration["state"])
        await self.outputs(page, demonstration["outputs"])
        self.passed += 1

    async def run(self) -> dict:
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(chromium_sandbox=True)
                context = await browser.new_context(accept_downloads=False)
                await context.route("**/*", self.route)
                page = await context.new_page()
                page.set_default_timeout(2000)
                page.on(
                    "pageerror", lambda error: self.reject("JavaScript error: " + str(error)[:200])
                )
                page.on(
                    "console",
                    lambda message: (
                        self.reject("Candidate console error.") if message.type == "error" else None
                    ),
                )
                page.on("popup", lambda _: self.reject("Candidate attempted a popup."))
                async with asyncio.timeout(15):
                    await self.exercise(page)
                await browser.close()
        except Exception as exc:
            self.reject(f"Browser verification failed: {type(exc).__name__}.")
        return {"approved": not self.reasons, "checks_passed": self.passed, "reasons": self.reasons}


if __name__ == "__main__":
    payload = json.loads(sys.stdin.buffer.read(500_001))
    sys.stdout.write(json.dumps(asyncio.run(_Verification(payload).run())))
