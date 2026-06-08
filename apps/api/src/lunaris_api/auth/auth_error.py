class AuthError(Exception):
    """An end-user token is missing, malformed, or fails verification.

    Raised by the token verifier; the FastAPI layer maps it to a 401 so verification logic stays
    free of HTTP concerns.
    """
