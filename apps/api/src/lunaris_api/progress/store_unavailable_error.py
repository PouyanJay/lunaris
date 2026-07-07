class ProgressStoreUnavailableError(Exception):
    """The progress backend failed a read — the caller maps it to a recoverable 503 (mirroring
    ``RunHistoryUnavailableError``), never a raw 500 that would lose its CORS headers."""
