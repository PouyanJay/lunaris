from threading import Lock
from uuid import uuid4
from weakref import WeakKeyDictionary

from ..protocols import IKnowledgeStore, ISessionStore
from ..stale_answer_error import StaleAnswerError
from .models.claim import GraphClaim
from .models.local_state import LocalTransactionState
from .models.mutation import SessionMutation

_states: WeakKeyDictionary = WeakKeyDictionary()
_states_lock = Lock()


class LocalGraphTransactions:
    """Offline coordination for shared in-memory stores; durable deployments use the SQL backend."""

    def __init__(self, sessions: ISessionStore, knowledge: IKnowledgeStore) -> None:
        self._sessions, self._knowledge = sessions, knowledge
        with _states_lock:
            self._state = _states.setdefault(knowledge, LocalTransactionState())

    def acquire(self, graph_id: str, *, owner_id: str | None) -> GraphClaim | None:
        key = (owner_id, graph_id)
        if not self._state.lock.acquire(blocking=False):
            return None
        try:
            if key in self._state.claims:
                return None
            claim = GraphClaim(graph_id, owner_id, uuid4().hex)
            self._state.claims[key] = claim
            return claim
        finally:
            self._state.lock.release()

    def renew(self, claim: GraphClaim) -> bool:
        with self._state.lock:
            return self._state.claims.get((claim.owner_id, claim.graph_id)) == claim

    def paid(self, claim: GraphClaim, operation_key: str) -> bool:
        with self._state.lock:
            if not self.renew(claim):
                raise StaleAnswerError("Graph transaction expired")
            key = (claim.owner_id, claim.graph_id, operation_key)
            if key in self._state.receipts:
                return False
            self._state.receipts.add(key)
            return True

    def commit(self, claim: GraphClaim, mutation: SessionMutation) -> None:
        with self._state.lock:
            if not self.renew(claim):
                raise StaleAnswerError("Graph transaction expired")
            if mutation.forget:
                self._knowledge.forget(claim.graph_id, owner_id=claim.owner_id)
            elif mutation.delete_session:
                self._sessions.delete(mutation.delete_session, owner_id=claim.owner_id)
            elif mutation.session:
                self._save(claim, mutation)
            else:
                raise ValueError("Empty session transaction")

    def _save(self, claim: GraphClaim, mutation: SessionMutation) -> None:
        session = mutation.session
        assert session is not None
        if session.graph_id != claim.graph_id:
            raise ValueError("Wrong graph transaction scope")
        self._sessions.save(session, owner_id=claim.owner_id, expect_turns=mutation.expected_turns)
        if mutation.knowledge is not None:
            self._knowledge.save(mutation.knowledge, owner_id=claim.owner_id)

    def release(self, claim: GraphClaim) -> None:
        with self._state.lock:
            if self.renew(claim):
                del self._state.claims[(claim.owner_id, claim.graph_id)]
