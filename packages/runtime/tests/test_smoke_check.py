"""T1b (keyless-fallbacks): the startup tool-calling smoke check for the keyless model.

The keyless fallback's one residual risk is tool-call reliability, so an operator can probe it
before serving: a trivial bind-tools call that reports whether the model tool-calls (OK), reachable
won't tool-call (NO_TOOL_CALL), or can't be reached at all (UNREACHABLE). It is best-effort — any
error degrades to UNREACHABLE and is logged, never raised, so a missing local runtime is a warning,
not a crash.
"""

from langchain_core.messages import AIMessage
from lunaris_runtime.resilience import SmokeCheckResult, keyless_tool_calling_smoke_check
from lunaris_runtime.resilience import smoke_check as smoke_check_module


class _FakeBound:
    def __init__(self, response: object) -> None:
        self._response = response

    def invoke(self, _: object) -> object:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeModel:
    """Stands in for the keyless fallback model so the check is tested without a live runtime."""

    def __init__(self, response: object) -> None:
        self._response = response

    def bind_tools(self, _tools: object) -> _FakeBound:
        return _FakeBound(self._response)


def _patch_model(monkeypatch, response: object) -> None:
    monkeypatch.setattr(
        smoke_check_module, "build_keyless_chat_model", lambda: _FakeModel(response)
    )


def test_a_valid_tool_call_reports_ok(monkeypatch) -> None:
    _patch_model(
        monkeypatch,
        AIMessage(
            content="",
            tool_calls=[{"type": "tool_call", "name": "echo", "args": {"value": 1}, "id": "c1"}],
        ),
    )

    assert keyless_tool_calling_smoke_check() is SmokeCheckResult.OK


def test_a_reachable_model_that_does_not_tool_call_reports_no_tool_call(monkeypatch) -> None:
    _patch_model(monkeypatch, AIMessage(content="sure, the value is 1", tool_calls=[]))

    assert keyless_tool_calling_smoke_check() is SmokeCheckResult.NO_TOOL_CALL


def test_an_unreachable_endpoint_reports_unreachable_without_raising(monkeypatch) -> None:
    # A dead local runtime must not crash startup — it degrades to a logged warning.
    _patch_model(monkeypatch, ConnectionError("connection refused"))

    assert keyless_tool_calling_smoke_check() is SmokeCheckResult.UNREACHABLE
