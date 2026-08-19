from ..graph.schema import ConceptNode, MasteryCriterion
from .schema import SimApp
from .stub_sim_path import STUB_SIM_PATH

_STUB_APP_ID = "lunaris.sim.stub"


class StubSimRegistry:
    """A registry with exactly one simulator, which fits every criterion that asks for one.

    **Nothing real is behind it, and that is the point** (A3). What it proves is the socket:
    something registers a simulator, the turn mounts it, and what the learner does in it comes back.
    Phase 3 replaces this class — a real registry knows which sims have actually been built and
    verified, and answers ``None`` for every concept whose sim does not exist yet.

    It answers for *any* sim-needing criterion on purpose. A stub that matched one hard-coded
    concept would make every test of this tier a test of that concept, and the offline pipeline
    would only ever exercise the socket on a fixture somebody remembered to name.
    """

    def __init__(self, *, base_url: str = "") -> None:
        # Prefixed rather than baked in, so a caller that knows its own origin (the API composing a
        # session for a browser) can hand over an absolute URL while tests keep a relative one.
        self._base_url = base_url.rstrip("/")

    def app_for(self, node: ConceptNode, criterion: MasteryCriterion) -> SimApp | None:
        if not criterion.needs_sim:
            # Never diverts a criterion that a text answer can already carry: that path has been
            # evaluated end to end (P2a's keyed eval) and this one has not.
            return None
        return SimApp(
            app_id=_STUB_APP_ID,
            url=f"{self._base_url}{STUB_SIM_PATH}",
            # Named after the concept it stands in for, so a screenshot of the socket cannot be
            # mistaken for a screenshot of a simulator that knows anything about the subject.
            title=f"{node.name} — placeholder simulator",
        )
