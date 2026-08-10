from lunaris_runtime.persistence import PersistenceError


class SessionFormatError(PersistenceError):
    """A stored session this build cannot parse.

    A subclass rather than a sibling, for two reasons. ``guard`` lets ``PersistenceError`` through
    untranslated, so this survives the store boundary it is raised inside; and every caller that
    only knows about storage failing keeps working, leaving the distinction available to the one
    place that wants it.

    That place is the router, because the two failures want opposite things from a learner. Storage
    being down is worth retrying and ends by itself; a row written by a schema this build no longer
    understands never will, and telling somebody to try again is an invitation to reload forever.
    """
