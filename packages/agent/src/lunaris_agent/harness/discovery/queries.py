"""Deterministic query planning for discovery: one subject-keyed search per concept.

Query *planning* needs no model call — narrow, KC-keyed queries are derived from the curriculum
(cheaper, testable, and structurally **keyed to the subject, never to a written claim**, since
discovery runs before any lesson is authored). The bounded budget does the real cost-capping.
"""

from dataclasses import dataclass

from ..draft import CourseDraft


@dataclass(frozen=True)
class DiscoveryQuery:
    """A planned search: the query string and the KC it seeks evidence for."""

    text: str
    kc_id: str


def build_discovery_queries(draft: CourseDraft) -> list[DiscoveryQuery]:
    """One query per concept, anchored to the subject so hits are on-topic, not keyword noise.

    Ordered hardest-concept-first so a bounded search budget spends on the goal-bearing concepts
    before the foundational ones; deterministic and re-runnable (the reflect loop re-plans from the
    still-uncovered KCs).
    """
    subject = draft.brief.subject if draft.brief else draft.topic
    concepts = sorted(draft.concepts, key=lambda kc: kc.difficulty, reverse=True)
    return [DiscoveryQuery(f"{kc.label} {subject}".strip(), kc.id) for kc in concepts]
