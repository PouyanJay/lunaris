from typing import Protocol


class IUserVerifier(Protocol):
    """Verifies an end-user access token and returns the user id, or raises ``AuthError``.

    The seam the composition root wires implementations through (HS256 today; ES256/JWKS next), so
    the auth dependency never depends on a concrete verifier.
    """

    def verify(self, token: str) -> str: ...
