"""Retention keeps retrying after storage failures and shuts down without hanging the API."""

import asyncio

import pytest
from lunaris_api.live.voice.maintenance import run_voice_cleanup


async def test_retention_recovers_after_failure_and_cancels_cleanly():
    swept = asyncio.Event()

    class Cleanup:
        calls = 0

        async def run_once(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("private-storage-error")
            swept.set()
            return 1

    cleanup = Cleanup()
    task = asyncio.create_task(run_voice_cleanup(cleanup, interval_s=0.001))
    try:
        await asyncio.wait_for(swept.wait(), timeout=1)
        assert cleanup.calls >= 2
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_api_lifespan_schedules_retention_even_when_voice_is_disabled(tmp_path, monkeypatch):
    from dataclasses import replace

    from _live_stack import settings_for
    from fastapi import FastAPI
    from lunaris_api import app as app_module
    from lunaris_api.live.voice import retention

    started = asyncio.Event()
    stopped = asyncio.Event()
    settings = replace(
        settings_for(tmp_path),
        live_session_budget_s=7200,
        supabase_url="http://local.invalid",
        supabase_service_role_key="fixture",
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(retention, "VoiceAudioCleanup", lambda _: object())

    async def run_cleanup(_):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(retention, "run_voice_cleanup", run_cleanup)
    async with app_module._lifespan(FastAPI()):
        await asyncio.wait_for(started.wait(), timeout=1)
    assert stopped.is_set()
