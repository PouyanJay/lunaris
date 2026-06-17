import jwt

from .auth_error import AuthError
from .user_claims import UserClaims
from .user_verifier import IUserVerifier


class CompositeUserVerifier:
    """Routes a token to the right verifier by its header ``alg``: HS256 (local / shared-secret) vs
    asymmetric ES256/RS256 (cloud JWKS).

    Lets one deployment accept both token families — local Supabase signs HS256, cloud projects sign
    ES256 — without callers knowing which path verified them.

    Each arm holds only its own key material (HMAC secret vs. JWKS public keys), so the classic
    alg-confusion attack (claim ``alg: HS256`` and pass a public key as the HMAC secret) has no
    shared key to exploit. Keep that invariant: never wire the JWKS keys into the HS256 arm.
    """

    def __init__(self, *, hs256: IUserVerifier | None, asymmetric: IUserVerifier | None) -> None:
        self._hs256 = hs256
        self._asymmetric = asymmetric

    def verify(self, token: str) -> UserClaims:
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token header") from exc
        verifier = self._hs256 if algorithm == "HS256" else self._asymmetric
        if verifier is None:
            # Generic message — the unverified alg is attacker-controlled, so don't echo it.
            raise AuthError("unsupported token type") from None
        return verifier.verify(token)
