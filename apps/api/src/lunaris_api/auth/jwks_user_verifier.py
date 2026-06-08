import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from ._supabase import AUDIENCE, JWKS_PATH
from .auth_error import AuthError

# Asymmetric algorithms Supabase signing keys use (newer cloud projects default to ES256).
_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
# Re-fetch the JWKS at most this often, so a rotated signing key is picked up without a restart.
_JWKS_CACHE_LIFESPAN_SECONDS = 300


class JwksUserVerifier:
    """Verifies an asymmetric Supabase Auth JWT (ES256/RS256) against the project's JWKS endpoint.

    Cloud projects publish their signing keys at ``{project_url}/auth/v1/.well-known/jwks.json``.
    The PyJWKClient fetches and caches them (keyed by ``kid``); the cache expires every
    ``_JWKS_CACHE_LIFESPAN_SECONDS`` so a key rotation is honoured without a restart. Steady-state
    verification makes no network call.
    """

    def __init__(self, supabase_url: str) -> None:
        self._client = PyJWKClient(
            f"{supabase_url}{JWKS_PATH}", lifespan=_JWKS_CACHE_LIFESPAN_SECONDS
        )

    def verify(self, token: str) -> str:
        try:
            signing_key = self._client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=_ASYMMETRIC_ALGORITHMS,
                audience=AUDIENCE,
            )
        except (jwt.PyJWTError, PyJWKClientError) as exc:
            # Generic message; library/fetch detail stays in the chained cause, never surfaced.
            raise AuthError("token verification failed") from exc
        subject = claims.get("sub")
        if not subject:
            raise AuthError("token has no subject")
        return str(subject)
