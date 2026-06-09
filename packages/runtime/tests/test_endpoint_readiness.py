"""T8 (keyless-fallbacks): readiness probe for the keyless LLM endpoint (the serverless GPU).

The keyless model is served by a self-hosted, scale-to-zero GPU endpoint, so the first build after
idle waits while the GPU provisions. This probe turns that into a signal the UI can show: a fast
health check whose result distinguishes "ready", "provisioning" (warming up — a 503 while the model
loads, or a short-probe timeout while the replica scales from zero), and "unreachable" (nothing
configured / wrong URL). Best-effort: it never raises.
"""

from collections.abc import Awaitable, Callable

import httpx
import pytest
from lunaris_runtime.resilience import ReadinessStatus, probe_keyless_llm_endpoint


def _returns(status_code: int) -> Callable[[str], Awaitable[int]]:
    """An injectable health-GET that returns ``status_code`` (no I/O — a plain factory)."""

    async def get(_url: str) -> int:
        return status_code

    return get


async def test_a_200_health_response_is_ready(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")

    # Act
    status = await probe_keyless_llm_endpoint(get=_returns(200))

    # Assert
    assert status is ReadinessStatus.READY


async def test_a_503_loading_response_is_provisioning(monkeypatch) -> None:
    # Arrange — llama.cpp answers 503 while the model loads into VRAM (up but warming).
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")

    # Act
    status = await probe_keyless_llm_endpoint(get=_returns(503))

    # Assert
    assert status is ReadinessStatus.PROVISIONING


@pytest.mark.parametrize("code", [400, 401, 404, 500])
async def test_an_unexpected_status_code_is_unreachable(monkeypatch, code: int) -> None:
    # Arrange — only 200/503 are meaningful; anything else means we can't trust it's the GPU server.
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")

    # Act
    status = await probe_keyless_llm_endpoint(get=_returns(code))

    # Assert
    assert status is ReadinessStatus.UNREACHABLE


async def test_a_timeout_is_provisioning(monkeypatch) -> None:
    # Arrange — a scale-to-zero GPU queues the first request while the replica spins up; a short
    # probe times out — read as "waking up", not a hard failure (the probe also pre-warms it).
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")

    async def get(_url: str) -> int:
        raise httpx.TimeoutException("probe timed out")

    # Act
    status = await probe_keyless_llm_endpoint(get=get)

    # Assert
    assert status is ReadinessStatus.PROVISIONING


async def test_a_connection_error_is_unreachable(monkeypatch) -> None:
    # Arrange — no endpoint configured / wrong host → nothing to provision.
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")

    async def get(_url: str) -> int:
        raise httpx.ConnectError("connection refused")

    # Act
    status = await probe_keyless_llm_endpoint(get=get)

    # Assert
    assert status is ReadinessStatus.UNREACHABLE


async def test_the_health_url_drops_the_openai_v1_suffix(monkeypatch) -> None:
    # Arrange — the OpenAI base is …/v1; llama.cpp's health route is at the host root.
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu:8080/v1")
    seen: list[str] = []

    async def get(url: str) -> int:
        seen.append(url)
        return 200

    # Act
    await probe_keyless_llm_endpoint(get=get)

    # Assert — {host}/health, not {host}/v1/health.
    assert seen == ["http://gpu:8080/health"]
