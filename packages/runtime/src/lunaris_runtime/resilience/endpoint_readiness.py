"""Readiness probe for the keyless LLM endpoint — the serverless GPU (keyless-fallbacks T8).

The keyless model runs on a self-hosted, scale-to-zero GPU endpoint, so the first build after idle
waits while the GPU provisions (the replica scales from zero, then the model loads into VRAM). This
turns that wait into a signal the UI can show, from a single fast health check:

- **READY** — the endpoint answered 200; the model is loaded and can serve.
- **PROVISIONING** — it's warming up: a 503 (llama.cpp's "loading model"), or the short probe timed
  out while a scaled-to-zero replica spins up (the probe itself nudges the cold start along).
- **UNREACHABLE** — nothing answered (no endpoint wired, wrong URL): there is no GPU to provision.

Best-effort: every failure maps to a status, never an exception. A probe callable can be injected
for tests, so the default ``httpx`` path is never exercised under test.
"""

import os
from collections.abc import Awaitable, Callable
from enum import StrEnum

import httpx
import structlog

logger = structlog.get_logger()

# Must match llm_client's fallback default so the probe hits the same endpoint the build will use.
_DEFAULT_FALLBACK_BASE_URL = "http://localhost:8080/v1"
# Short on purpose: a ready endpoint answers in milliseconds; anything slower is a cold start to
# surface as "provisioning" rather than block on.
_PROBE_TIMEOUT_S = 3.0

# An injectable health-GET: takes the health URL, returns the HTTP status code, and raises
# httpx errors (TimeoutException / transport errors) the prober maps to a readiness status.
HealthGet = Callable[[str], Awaitable[int]]


class ReadinessStatus(StrEnum):
    """Whether the keyless GPU endpoint can serve right now."""

    READY = "ready"
    PROVISIONING = "provisioning"
    UNREACHABLE = "unreachable"
    # The caller's LLM is keyed (a hosted API), so there is no GPU to provision. Set by the API
    # layer, which knows the caller's key state; the probe itself never returns this.
    NOT_APPLICABLE = "not_applicable"


def _health_url(base_url: str) -> str:
    """The health route for an OpenAI-compatible base URL: ``{host}/health`` (the route sits at the
    host root, not under the ``/v1`` API prefix)."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return f"{root}/health"


async def _default_get(url: str) -> int:
    """GET ``url`` with a short timeout and return its status code."""
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
        response = await client.get(url)
    return response.status_code


async def probe_keyless_llm_endpoint(*, get: HealthGet | None = None) -> ReadinessStatus:
    """Probe the configured keyless LLM endpoint's health and classify it.

    Reads ``LUNARIS_FALLBACK_LLM_BASE_URL`` (the same endpoint the keyless build uses), derives the
    health route, and GETs it. 200 → READY; 503 → PROVISIONING; a timeout → PROVISIONING (a
    scale-to-zero replica is waking, and this probe nudges it); any other error → UNREACHABLE.
    """
    url = _health_url(os.getenv("LUNARIS_FALLBACK_LLM_BASE_URL", _DEFAULT_FALLBACK_BASE_URL))
    do_get = get or _default_get
    try:
        status_code = await do_get(url)
    except httpx.TimeoutException:
        return ReadinessStatus.PROVISIONING
    except Exception:
        # warning, not info: an UNREACHABLE keyless endpoint is a misconfiguration the operator
        # should see (matches the other keyless providers' failure logging).
        logger.warning("keyless_endpoint_unreachable", exc_info=True)
        return ReadinessStatus.UNREACHABLE
    if status_code == 200:
        return ReadinessStatus.READY
    if status_code == 503:
        return ReadinessStatus.PROVISIONING
    return ReadinessStatus.UNREACHABLE
