from dataclasses import dataclass


@dataclass(frozen=True)
class SiblingContractDigest:
    """A compact, plan-time view of an UPSTREAM sibling video's scene contract.

    When a lesson sits downstream of others in the course's prerequisite DAG, its planner is given a
    digest of each upstream video it depends on — what that video already covers — so the new plan
    builds on them, reuses their terminology, and never re-explains or contradicts them (instead of
    re-inventing in a vacuum, which is what trips the factual gate on a blind Fresh-take re-plan).

    Deliberately a small summary, not the whole contract: the planner needs *what an upstream
    covers*, not its every beat, and the prompt has a token budget. ``covers`` is the one-line
    "what this video teaches" line; richer fields (per-scene archetypes, key terms) are folded in
    by the digest builder.
    """

    lesson_title: str
    covers: str
