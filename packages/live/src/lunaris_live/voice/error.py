class VoiceError(Exception):
    """A safe voice refusal; the text session can continue."""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
