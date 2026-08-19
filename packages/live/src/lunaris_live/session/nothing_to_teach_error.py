from datetime import datetime


class NothingToTeachError(ValueError):
    """The map has nothing for a session to open on: the director's first move would be to close.

    An empty map, one whose teaching order names concepts it does not have — or, from P2c T6, a
    finished map whose reviews are not yet due: the learner demonstrated everything, and the close
    told them the day to come back. ``next_review_at`` is that day when there is one, so the caller
    can say "come back Thursday" rather than "something went wrong". A ``ValueError`` still, as it
    was before it had a name, so callers that refused on that keep refusing.
    """

    def __init__(self, graph_id: str, *, next_review_at: datetime | None = None) -> None:
        super().__init__(f"graph {graph_id} has nothing to teach")
        self.graph_id = graph_id
        self.next_review_at = next_review_at
