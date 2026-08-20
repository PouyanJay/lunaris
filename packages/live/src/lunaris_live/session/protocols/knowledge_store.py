from typing import Protocol

from ..schema import LearnerModel


class IKnowledgeStore(Protocol):
    """Persistence for what a learner knows about one map.

    Unlike the session and graph stores, ``load`` **never raises for absence**: a learner opening
    their first session on a map genuinely has no history, and that is the common case rather
    than an error. It answers an empty model, so callers do not each write the same try/except —
    one of them would eventually get it wrong, and getting it wrong means treating "no history"
    as a failure at the exact moment a learner starts.

    ``owner_id`` scopes it, and unscoped means *unowned* rather than *see everything*: another
    learner's beliefs must never be returned, because acting on them would have the director skip
    concepts this learner has never seen.
    """

    def save(self, model: LearnerModel, *, owner_id: str | None = None) -> None: ...

    def load(self, graph_id: str, *, owner_id: str | None = None) -> LearnerModel: ...

    def forget(self, graph_id: str, *, owner_id: str | None = None) -> None:
        """Clear what this owner knows about one map, leaving every other map untouched.

        Never raises for absence, for the same reason ``load`` does not: "forget this" on a topic
        with nothing to forget has already happened, and a learner pressing it twice should not meet
        an error the second time. Scoped like the rest, and unscoped means *unowned* rather than
        *everyone*, which matters more here than anywhere: a reset that reached past its owner
        would clear somebody else's progress with no way to get it back.
        """
        ...
