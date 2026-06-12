"""Explain API: plain-language explanations of transcript blobs, gated on a reachable Anthropic key.

The explainer is injected (a stub here, the real Claude one in production), so the route's contract
(200 with an explanation, 503 when unavailable or the model fails, 422 on a bad payload, and the
``supportsExplain`` settings flag) is proven with no API key.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_explain_binding, get_secret_store
from lunaris_api.explain import ExplainBinding, IExplainer
from lunaris_api.schemas.explain import MAX_EXPLAIN_CONTENT
from lunaris_api.secrets import SecretStore


class _StubExplainer:
    """Records its calls and returns a fixed explanation — no model, no key."""

    def __init__(self, text: str = "It orders concepts so prerequisites come first.") -> None:
        self._text = text
        self.calls: list[tuple[str, str | None]] = []

    async def explain(self, content: str, context: str | None) -> str:
        self.calls.append((content, context))
        return self._text


def _build_client(
    tmp_path: Path, explainer: IExplainer | None, *, draft_tier_enabled: bool = True
) -> httpx.AsyncClient:
    app = create_app()
    env_file = tmp_path / ".env"
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=env_file,
        draft_tier_enabled=draft_tier_enabled,
    )
    app.dependency_overrides[get_secret_store] = lambda: SecretStore(env_file)
    binding = (
        ExplainBinding(explainer=explainer, source="hosted", credentials=None)
        if explainer is not None
        else None
    )
    app.dependency_overrides[get_explain_binding] = lambda: binding
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, _StubExplainer()) as http_client:
        yield http_client


async def test_explain_returns_a_plain_language_explanation(tmp_path: Path) -> None:
    # Arrange
    stub = _StubExplainer("These judge whether one concept must be learned before another.")
    async with _build_client(tmp_path, stub) as client:
        # Act
        response = await client.post(
            "/api/explain",
            json={"content": '{"is_prereq": true, "strength": 0.85}', "context": "Graph"},
        )

    # Assert — the explanation comes back, and the blob + context were passed through verbatim.
    assert response.status_code == 200
    assert response.json() == {
        "explanation": "These judge whether one concept must be learned before another.",
        "source": "hosted",
    }
    assert stub.calls == [('{"is_prereq": true, "strength": 0.85}', "Graph")]


async def test_explain_response_carries_a_request_id(client: httpx.AsyncClient) -> None:
    # Arrange — the shared client fixture wires a StubExplainer (explain succeeds).

    # Act
    response = await client.post("/api/explain", json={"content": "{}"})

    # Assert — correlation everywhere: the call succeeded AND is traceable across the logs.
    assert response.status_code == 200
    assert response.json()["explanation"]
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-Id"])


async def test_explain_forwards_content_with_no_context(tmp_path: Path) -> None:
    # Arrange — a request omitting context (the optional field defaults to None).
    stub = _StubExplainer()
    async with _build_client(tmp_path, stub) as client:
        # Act
        await client.post("/api/explain", json={"content": '{"k": 1}'})

    # Assert — the content is forwarded with context defaulted to None.
    assert stub.calls == [('{"k": 1}', None)]


async def test_explain_is_503_when_no_explainer_is_available(tmp_path: Path) -> None:
    # Arrange — neither tier available → the binding resolves to None.
    async with _build_client(tmp_path, None) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert — fails closed, not a 500.
    assert response.status_code == 503


async def test_explain_degrades_to_503_when_the_model_fails(tmp_path: Path) -> None:
    # Arrange — an explainer whose model call raises.
    class _FailingExplainer:
        async def explain(self, content: str, context: str | None) -> str:
            raise RuntimeError("model unreachable")

    async with _build_client(tmp_path, _FailingExplainer()) as client:
        # Act
        response = await client.post("/api/explain", json={"content": "{}"})

    # Assert — the failure is contained as a clean 503 (no leaked detail).
    assert response.status_code == 503
    assert "explanation" in response.json()["detail"].lower()


async def test_explain_rejects_empty_content(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.post("/api/explain", json={"content": ""})

    # Assert
    assert response.status_code == 422


async def test_explain_rejects_oversized_content(client: httpx.AsyncClient) -> None:
    # Act — one character over the schema's MAX_EXPLAIN_CONTENT fence.
    response = await client.post("/api/explain", json={"content": "x" * (MAX_EXPLAIN_CONTENT + 1)})

    # Assert
    assert response.status_code == 422


async def test_settings_reports_explain_available_when_the_key_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    async with _build_client(tmp_path, _StubExplainer()) as client:
        # Act
        body = (await client.get("/api/settings")).json()

    # Assert
    assert body["supportsExplain"] is True


async def test_settings_reports_explain_unavailable_without_a_key_or_keyless_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — no key AND the keyless tier off: neither explain tier can answer.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async with _build_client(tmp_path, _StubExplainer(), draft_tier_enabled=False) as client:
        # Act
        body = (await client.get("/api/settings")).json()

    # Assert
    assert body["supportsExplain"] is False


async def test_settings_reports_explain_available_keyless_when_draft_tier_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — no key, but the keyless server tier can answer (local-intelligence Phase 1).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async with _build_client(tmp_path, _StubExplainer(), draft_tier_enabled=True) as client:
        # Act
        body = (await client.get("/api/settings")).json()

    # Assert
    assert body["supportsExplain"] is True


async def test_settings_keyless_caller_gets_any_tier_but_not_hosted_explain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — keyless with the Draft tier on: the reader can explain, the transcript cannot.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async with _build_client(tmp_path, _StubExplainer(), draft_tier_enabled=True) as client:
        # Act
        body = (await client.get("/api/settings")).json()

    # Assert — supportsExplain = any tier; supportsHostedExplain = the transcript's stricter gate.
    assert body["supportsExplain"] is True
    assert body["supportsHostedExplain"] is False


async def test_settings_keyed_caller_gets_both_explain_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — keyed: both surfaces explain on the hosted tier.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    async with _build_client(tmp_path, _StubExplainer(), draft_tier_enabled=True) as client:
        # Act
        body = (await client.get("/api/settings")).json()

    # Assert
    assert body["supportsExplain"] is True
    assert body["supportsHostedExplain"] is True
