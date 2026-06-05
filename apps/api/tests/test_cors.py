"""CORS preflight for the web client.

The Settings panel saves a secret with PUT and clears it with DELETE. A browser sends a CORS
preflight (OPTIONS) before those non-simple methods; if the API's allowed-methods list omits them,
the preflight 400s and the browser's fetch rejects with a network error ("Could not reach the
settings service") — even though the endpoint itself works. These tests pin that the preflight for
every method the web actually uses is allowed from the dev origin.
"""

import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from starlette.testclient import TestClient

_ORIGIN = "http://localhost:5173"


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=".",
        cors_origins=(_ORIGIN,),
        env_file=".env",
    )
    return TestClient(app)


def _preflight(client: TestClient, path: str, method: str) -> int:
    response = client.options(
        path,
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )
    return response.status_code


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/settings/secrets/anthropic", "PUT"),  # save a key (the reported bug)
        ("/api/settings/secrets/anthropic", "DELETE"),  # clear a key
        ("/api/courses", "POST"),  # build a course
        ("/api/courses/stream", "GET"),  # SSE build stream
    ],
)
def test_cors_preflight_allows_every_method_the_web_uses(
    client: TestClient, path: str, method: str
) -> None:
    # A 200 means the browser will proceed with the real request; a 400 ("Disallowed CORS method")
    # is what surfaces as a network error in the UI.
    assert _preflight(client, path, method) == 200


def test_cors_preflight_advertises_put_and_delete(client: TestClient) -> None:
    # The cached allow-methods header must list the non-simple methods, not just GET/POST.
    response = client.options(
        "/api/settings/secrets/anthropic",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    allowed = response.headers.get("access-control-allow-methods", "")
    assert "PUT" in allowed
    assert "DELETE" in allowed
