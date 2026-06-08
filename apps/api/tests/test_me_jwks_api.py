"""Integration test for the cloud auth path — ``GET /api/me`` verifying an asymmetric (ES256)
Supabase JWT against a JWKS endpoint.

Hermetic: generates an EC P-256 keypair, serves the public key as a JWKS from a localhost HTTP
server (standing in for ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``), mints an ES256 token with
the private key, and asserts the real router → dependency → JWKS-client → verify path accepts it.
This is the production path for cloud Supabase, which signs with ES256 rather than the local HS256.
"""

import json
import time
from collections.abc import AsyncIterator, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation

_TEST_USER_ID = "22222222-2222-2222-2222-222222222222"
_KID = "test-es256-key"


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def jwks_server(signing_key: ec.EllipticCurvePrivateKey) -> Iterator[str]:
    jwk = json.loads(ECAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update({"kid": _KID, "use": "sig", "alg": "ES256"})
    body = json.dumps({"keys": [jwk]}).encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.endswith("/auth/v1/.well-known/jwks.json"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args: object) -> None:  # silence the server's stderr logging
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()


def _mint_es256_token(
    signing_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str = _TEST_USER_ID,
    kid: str = _KID,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, signing_key, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
async def client(jwks_server: str, tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_url=jwks_server,  # the verifier derives the JWKS URL from this
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_get_me_accepts_es256_token_via_jwks(
    client: httpx.AsyncClient, signing_key: ec.EllipticCurvePrivateKey
) -> None:
    # Arrange
    token = _mint_es256_token(signing_key)

    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 200
    assert response.json() == {"userId": _TEST_USER_ID}


async def test_get_me_rejects_es256_token_signed_by_unknown_key(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — a token signed by a key the JWKS endpoint does not publish
    intruder_key = ec.generate_private_key(ec.SECP256R1())
    token = _mint_es256_token(intruder_key)

    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 401
