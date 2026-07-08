class BookmarkStoreUnavailableError(Exception):
    """The bookmarks backend can't be reached — callers answer a recoverable 503."""
