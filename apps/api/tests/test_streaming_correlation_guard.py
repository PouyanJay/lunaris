"""Correlation on a streaming endpoint depends on the app's middleware stack staying plain ASGI.

Both of Live's streams — the compile stream (Phase 1) and the session stream (Phase 2b) — bind their
correlation ids in the endpoint body and then log from inside the response generator. That works
because Starlette runs the body in the same task, so the binding is still in scope when the
generator finally runs.

``BaseHTTPMiddleware`` breaks it. Its ``call_next`` returns as soon as the *headers* are ready, long
before the body is iterated, so a middleware doing the documented

    try:
        bind_contextvars(request_id=…)
        return await call_next(request)
    finally:
        clear_contextvars()

clears the binding *before* a single frame is produced. Every streaming endpoint silently loses its
correlation while every non-streaming one keeps it — which is the worst possible shape for a bug,
because the surfaces you would check first still look right.

PYTHON.md's own correlation-middleware example is exactly that pattern, so this is a plausible
future addition rather than a hypothetical. This test is here so it fails loudly at the moment
somebody adds one, instead of being rediscovered from a production incident on a path where the
whole point of the ids is triangulating across three runtimes.
"""

from lunaris_api.app import create_app
from starlette.middleware.base import BaseHTTPMiddleware


def test_no_base_http_middleware_is_registered() -> None:
    """If this fails, the correlation on every streaming endpoint has probably just been lost.

    The fix is not to delete this test: write the middleware as **plain ASGI**
    (``async def __call__(self, scope, receive, send)``), which wraps the whole response including
    the body, and correlation survives. Then relax this guard for that specific class, deliberately.
    """
    offenders = [
        middleware.cls.__name__
        for middleware in create_app().user_middleware
        if isinstance(middleware.cls, type) and issubclass(middleware.cls, BaseHTTPMiddleware)
    ]

    assert not offenders, (
        "BaseHTTPMiddleware returns before the response body is iterated, so anything it binds or "
        f"clears around `call_next` does not cover a streaming endpoint's frames: {offenders}. "
        "Write it as plain ASGI middleware instead."
    )
