from dataclasses import dataclass


@dataclass(frozen=True)
class SiblingContractDigest:
    """A compact, plan-time view of an UPSTREAM sibling video's scene contract.

    When a lesson sits downstream of others in the course's prerequisite DAG, its planner is given a
    digest of each upstream video it depends on — what that video already covers — so the new plan
    builds on them, reuses their terminology, and never re-explains or contradicts them (instead of
    re-inventing in a vacuum, which is what trips the factual gate on a blind Fresh-take re-plan).

    Deliberately a small summary, not the whole contract: the planner needs *what an upstream
    covers*, not its every beat, and the prompt has a token budget. ``covers`` is the upstream
    video's topic line; ``archetypes`` are the visual forms it used (so the downstream stays
    visually consistent); ``key_terms`` are the notable on-screen objects it introduced (so the
    downstream reuses them rather than re-defining). The two collections default empty so a digest
    can be built by hand from a title + covers line alone.
    """

    lesson_title: str
    covers: str
    archetypes: tuple[str, ...] = ()
    key_terms: tuple[str, ...] = ()
