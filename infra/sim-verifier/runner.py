"""Trusted browser driver. Candidate code stays in an opaque iframe inside Chromium's sandbox."""

import asyncio
import base64
import json
import sys
from collections import Counter, defaultdict

from playwright.async_api import Page, Route, async_playwright, expect

_HOST = "https://verifier.invalid/"
_APP = "https://candidate.invalid/"
_HOST_HTML = """<!doctype html><style>body{margin:0}iframe{width:100%;height:780px;border:0}</style>
<iframe sandbox="allow-scripts" src="https://candidate.invalid/"></iframe>
<script>
window.events = [];
addEventListener('message', e => {
  if(e.source === document.querySelector('iframe').contentWindow && window.events.length < 50)
    window.events.push(e.data);
});
</script>"""


def _circuit_terminals(geometry: dict) -> tuple[list, list]:
    positive, negative = geometry["positive"], geometry["negative"]
    assert positive[1] == positive[3] < negative[1] == negative[3], "Invalid source electrodes"
    assert positive[2] - positive[0] > negative[2] - negative[0] > 0, "Source polarity is unclear"
    source = [((p[0] + p[2]) / 2, p[1]) for p in (positive, negative)]
    assert source[0][0] == source[1][0], "Source terminals are misaligned"
    x, y, width, height = geometry["resistor"]
    assert width > 0 and height > 0, "Missing resistor body"
    resistor = [(x, y + height / 2), (x + width, y + height / 2)]
    return source, resistor


def _check_circuit_geometry(geometry: dict) -> None:
    source, resistor = _circuit_terminals(geometry)
    edges = [(tuple(wire[:2]), tuple(wire[2:])) for wire in geometry["wires"]]
    edges.extend((tuple(source), tuple(resistor)))
    degree = Counter(vertex for edge in edges for vertex in edge)
    assert degree and all(count == 2 for count in degree.values()), "Open or bypassed component"
    neighbors = defaultdict(set)
    for left, right in edges:
        assert left != right, "Zero-length wire"
        neighbors[left].add(right)
        neighbors[right].add(left)
    reached, pending = set(), [source[0]]
    while pending:
        vertex = pending.pop()
        if vertex not in reached:
            reached.add(vertex)
            pending.extend(neighbors[vertex] - reached)
    assert reached == set(degree), "Disconnected circuit components"
    _check_direction(geometry["arrow"], max(vertex[0] for vertex in degree))


def _check_direction(points: str, return_wire_x: float) -> None:
    arrow = [tuple(map(float, point.split(","))) for point in points.split()]
    assert len(arrow) == 3, "Invalid direction marker"
    tip, left, right = arrow
    assert tip[0] == return_wire_x, "Direction marker is off the return wire"
    assert left[1] == right[1] < tip[1], "Current direction contradicts source polarity"


class _Verification:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.reasons: list[str] = []
        self.passed = 0
        self.screenshots: list[str] = []

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
        await self.circuit(page, case["state"])
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

    async def circuit(self, page: Page, state: dict) -> None:
        if self.payload.get("renderer") != "series-resistor-v1":
            return
        host = page.frame_locator("iframe").locator('[data-lunaris-renderer="series-resistor-v1"]')
        await expect(host).to_be_visible()
        await expect(host.locator("svg")).to_be_visible()
        intact = await host.evaluate(
            """(host, expected) => {
            const reference=document.createElement('div');
            reference.innerHTML=expected.template;
            const state=expected.state;
            reference.querySelector('[data-circuit-voltage]').textContent=`${state.voltage} V`;
            reference.querySelector('[data-circuit-resistance]').textContent=
                `${state.resistance} Ω`;
            const current=state.voltage/state.resistance;
            reference.querySelector('[data-circuit-current]').textContent=
                `I = ${current.toFixed(2)} A`;
            reference.querySelector('[data-circuit-arrow]').style.visibility=current===0?'hidden':'visible';
            return host.shadowRoot.innerHTML===reference.innerHTML;
        }""",
            {"template": self.payload["renderer_template"], "state": state},
        )
        assert intact, "Assembled circuit subtree was modified"
        geometry = await host.evaluate("""host => {
            const root=host.shadowRoot;
            const line=e=>['x1','y1','x2','y2'].map(k=>Number(e.getAttribute(k)));
            const resistor=root.querySelector('[data-circuit-resistor]');
            return {wires:[...root.querySelectorAll('[data-circuit-wire]')].slice(0,20).map(line),
              positive:line(root.querySelector('[data-circuit-electrode="positive"]')),
              negative:line(root.querySelector('[data-circuit-electrode="negative"]')),
              resistor:['x','y','width','height'].map(k=>Number(resistor.getAttribute(k))),
              arrow:root.querySelector('[data-circuit-arrow]').getAttribute('points')};
        }""")
        _check_circuit_geometry(geometry)
        current = state["voltage"] / state["resistance"]
        await expect(host.locator("[data-circuit-current]")).to_have_text(f"I = {current:.2f} A")
        for field, unit in (("voltage", "V"), ("resistance", "Ω")):
            await expect(host.locator(f"[data-circuit-{field}]")).to_have_text(
                f"{state[field]:g} {unit}"
            )
        if current:
            await expect(host.locator("[data-circuit-arrow]")).to_be_visible()
        else:
            await expect(host.locator("[data-circuit-arrow]")).to_be_hidden()
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

    async def capture(self, page: Page) -> None:
        frame = page.frame_locator("iframe")
        height = await frame.locator("html").evaluate("el => el.scrollHeight")
        if height > 1560:
            raise ValueError("Simulator exceeds the bounded 1560px visual review canvas.")
        await page.locator("iframe").evaluate(
            "(el, height) => el.style.height = height + 'px'", height
        )
        await frame.locator("html").evaluate("() => window.scrollTo(0, 0)")
        await page.evaluate("window.scrollTo(0, 0)")
        self.screenshots.append(base64.b64encode(await page.screenshot(full_page=True)).decode())

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
        await self.capture(page)
        demonstration = self.payload["spec"]["cases"][0]
        await self.command(page, demonstration["state"])
        await self.outputs(page, demonstration["outputs"])
        await self.circuit(page, demonstration["state"])
        await self.capture(page)
        self.passed += 1

    async def run(self) -> dict:
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(chromium_sandbox=True)
                context = await browser.new_context(
                    accept_downloads=False, viewport={"width": 1100, "height": 800}
                )
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
            self.reject(f"Browser verification failed: {type(exc).__name__}. {str(exc)[:220]}")
        return {
            "approved": not self.reasons,
            "checks_passed": self.passed,
            "reasons": self.reasons,
            "screenshots": self.screenshots,
        }


if __name__ == "__main__":
    payload = json.loads(sys.stdin.buffer.read(500_001))
    sys.stdout.write(json.dumps(asyncio.run(_Verification(payload).run())))
