from collections.abc import Mapping
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph
from lunaris_live.session import (
    DirectorMove,
    IMaterialStore,
    ISimRegistry,
    ITutor,
    LearnerModel,
    MoveKind,
    node_of,
    predict_next,
    stage_criterion,
)
from lunaris_runtime.credentials import CredentialResolver, credentials_for
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.metering import drain_cost_scope, enter_cost_scope, make_cost_scope
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore
from lunaris_runtime.schema import CostSubjectType

from .prefetch_registry import PrefetchRegistry

logger = structlog.get_logger()

#: Why the tutor is asked for material ahead of time, in the words a trace reader gets. The move is
#: the director's *predicted* one; the material is the same for any first turn on the concept.
_AHEAD = "Asked for ahead of the learner, so the turn that reaches this concept has it ready."


class MaterialPrefetcher:
    """Asks the tutor for a concept's first-turn material before the learner gets there, and keeps
    it (P2c T4).

    One node ahead, never a fan-out: after each teaching turn the director's own prediction names
    the next concept, and unless its material is already kept or already being asked for, one
    illustrate call is made for it — under the session's own cost scope and the tenant's own keys,
    as its own run, and drained by itself when it ends. It can never cost the turn that scheduled it
    (nothing awaits it) and it can never cost anything but the session's money (the ceiling is read
    by the caller before scheduling).

    Built per request like the service, over a registry that is process-wide, so two requests do
    not ask for the same concept twice.
    """

    def __init__(
        self,
        tutor: ITutor,
        materials: IMaterialStore,
        *,
        registry: PrefetchRegistry,
        cost_event_store: ICostEventStore | None = None,
        subject_cost_store: ISubjectCostStore | None = None,
        credential_resolver: CredentialResolver | None = None,
        sims: ISimRegistry | None = None,
    ) -> None:
        self._tutor = tutor
        self._materials = materials
        self._registry = registry
        self._cost_event_store = cost_event_store
        self._subject_cost_store = subject_cost_store
        self._credential_resolver = credential_resolver
        self._sims = sims

    def prefetch_ahead_of(
        self,
        session_id: str,
        graph: ConceptGraph,
        model: LearnerModel,
        *,
        current: str,
        kept: Mapping[str, object],
        owner_id: str | None,
        profile: str | None = None,
    ) -> None:
        """Prefetch the concept the director would move to next after ``current``, if any."""
        next_id = predict_next(graph, model, current=current)
        if next_id is None:
            return
        self.prefetch_for_node(
            session_id, graph, next_id, kept=kept, owner_id=owner_id, profile=profile
        )

    def prefetch_for_node(
        self,
        session_id: str,
        graph: ConceptGraph,
        node_id: str,
        *,
        kept: Mapping[str, object],
        owner_id: str | None,
        profile: str | None = None,
    ) -> None:
        """Prefetch one named concept's first-turn material, unless it is kept or in flight."""
        if node_id in kept or self._registry.is_running(owner_id, graph.graph_id, node_id):
            return
        node = node_of(graph, node_id)
        if node is None:
            return
        run_id = uuid4().hex
        self._registry.start(
            owner_id,
            graph.graph_id,
            node_id,
            self._prefetch(
                session_id, graph, node_id, run_id=run_id, owner_id=owner_id, profile=profile
            ),
        )
        logger.info(
            "live.material.prefetch_scheduled",
            session_id=session_id,
            graph_id=graph.graph_id,
            node=node_id,
            prefetch_run_id=run_id,
        )

    async def _prefetch(
        self,
        session_id: str,
        graph: ConceptGraph,
        node_id: str,
        *,
        run_id: str,
        owner_id: str | None,
        profile: str | None,
    ) -> None:
        bind_run_id(run_id, session_id=session_id, graph_id=graph.graph_id)
        node = node_of(graph, node_id)
        if node is None:
            return
        move = DirectorMove(kind=MoveKind.INTRODUCE, node_id=node_id, reason=_AHEAD)
        cost = make_cost_scope(
            self._cost_event_store,
            self._subject_cost_store,
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=session_id,
            owner_id=owner_id,
        )
        try:
            with await credentials_for(self._credential_resolver, owner_id), enter_cost_scope(cost):
                parts = await self._tutor.illustrate(
                    move,
                    node,
                    topic=graph.topic,
                    criterion=stage_criterion(node, sims=self._sims),
                    already_said=(),
                    profile=profile,
                    run_id=run_id,
                )
        except Exception:
            # WARNING: the session goes on (the turn that reaches this concept asks live, as it
            # always did), but a prefetch that keeps failing is a prompt regression worth seeing.
            logger.warning("live.material.prefetch_failed", node=node_id, exc_info=True)
            return
        finally:
            if cost is not None:
                await drain_cost_scope(cost, self._cost_event_store, self._subject_cost_store)
        if parts.worked_example is None and parts.hint is None and not parts.practice:
            # Nothing came back (the tutor degraded): keeping an empty entry would make the turn
            # that reaches this concept skip asking, and get nothing.
            logger.info("live.material.prefetch_empty", node=node_id)
            return
        self._materials.save(graph.graph_id, node_id, parts, owner_id=owner_id)
        logger.info("live.material.prefetched", node=node_id)
