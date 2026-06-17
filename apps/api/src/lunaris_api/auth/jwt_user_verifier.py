import jwt

from ._supabase import AUDIENCE
from .auth_error import AuthError
from .user_claims import UserClaims


class JwtUserVerifier:
    """Verifies a Supabase Auth JWT (HS256) and returns its claims (the ``sub`` + ``email``).

    HS256 (the project's symmetric signing secret) covers local Supabase and any project on the
    shared secret. Asymmetric tokens (ES256 via JWKS, used by newer cloud projects) are handled by a
    sibling verifier added in a later task. Verification is local — no network call.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify(self, token: str) -> UserClaims:
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"], audience=AUDIENCE)
        except jwt.PyJWTError as exc:
            # Keep the message generic — the library text (e.g. "Signature verification failed") is
            # preserved via the chained cause for debugging, never surfaced to callers or logs.
            raise AuthError("token verification failed") from exc
        subject = claims.get("sub")
        if not subject:
            raise AuthError("token has no subject")
        email = claims.get("email")
        return UserClaims(user_id=str(subject), email=str(email) if email else None)
