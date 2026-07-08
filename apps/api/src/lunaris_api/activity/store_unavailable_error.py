class ActivityStoreUnavailableError(Exception):
    """The activity backend can't be reached — callers answer a recoverable 503."""
