"""Real Chromium → React host → HTTP session service → persisted exchange → iframe."""

import os
import re
import selectors
import socket
import subprocess
from pathlib import Path

import httpx
import pytest
from playwright.async_api import async_playwright, expect

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[2]


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def servers(tmp_path, request):
    api_port, web_port = _port(), _port()
    env = {**os.environ, "VITE_SUPABASE_URL": "", "VITE_SUPABASE_ANON_KEY": ""}
    config = getattr(request, "param", {})
    if config.get("auth"):
        env.update(
            VITE_SUPABASE_URL="https://identity.test", VITE_SUPABASE_ANON_KEY="public-test-key"
        )
    commands = [
        (
            [
                "uv",
                "run",
                "uvicorn",
                config.get("app", "sim_app") + ":app",
                "--app-dir",
                "tests/browser",
                "--port",
                str(api_port),
                "--lifespan",
                "off",
            ],
            ROOT,
        ),
        (
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
                "--strictPort",
            ],
            ROOT / "apps/web",
        ),
    ]
    processes = []
    with (tmp_path / "servers.log").open("w") as log:
        try:
            with selectors.DefaultSelector() as readiness:
                for command, cwd in commands:
                    process = subprocess.Popen(
                        command,
                        cwd=cwd,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        bufsize=0,
                    )
                    processes.append(process)
                    readiness.register(process.stdout, selectors.EVENT_READ)
                pending = {process.stdout for process in processes}
                buffers = dict.fromkeys(pending, b"")
                while pending:
                    events = readiness.select(timeout=60)
                    if not events:
                        pytest.fail("Server readiness timed out: " + str(buffers))
                    for key, _ in events:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            pytest.fail("Server exited before readiness: " + str(buffers))
                        log.write(chunk.decode(errors="replace"))
                        buffers[key.fileobj] = re.sub(
                            rb"\x1b\[[0-9;]*m", b"", buffers[key.fileobj] + chunk
                        )
                        if (
                            b"Uvicorn running on" in buffers[key.fileobj]
                            or b"Local:" in buffers[key.fileobj]
                        ):
                            pending.discard(key.fileobj)
                            readiness.unregister(key.fileobj)
            api, web = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
            assert httpx.get(f"{api}/api/healthz").is_success
            assert httpx.get(web).is_success
            yield api, web
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                process.wait(timeout=15)
                process.stdout.close()


async def test_learner_changes_state_tutor_demonstrates_and_reload_recovers(servers, tmp_path):
    api, web = servers
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"{web}/tests/sim.html?api={api}")
        frame = page.frame_locator("iframe")
        await expect(frame.get_by_role("button", name="Discuss this change")).to_be_enabled()
        slider = frame.get_by_label("x", exact=True)
        await slider.fill("4")
        await expect(frame.locator("#y")).to_have_text("y = 8")
        await frame.get_by_role("button", name="Discuss this change").click()
        await expect(page.get_by_role("status").filter(has_text="You set x to 4")).to_be_visible()
        await expect(slider).to_have_value("0")
        await expect(frame.locator("#y")).to_have_text("y = 0")
        await page.reload()
        await expect(frame.get_by_role("button", name="Discuss this change")).to_be_enabled()
        await expect(slider).to_have_value("0")
        await expect(page.get_by_role("status").filter(has_text="You set x to 4")).to_be_visible()
        await page.screenshot(path=str(tmp_path / "sim-roundtrip.png"), full_page=True)
        await browser.close()
