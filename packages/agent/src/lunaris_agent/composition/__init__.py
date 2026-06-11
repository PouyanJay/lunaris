"""The agent package's composition root, split by concern.

``_tiers`` resolves the worker/strong model tiers; ``_grounding`` builds the corpus-facing
collaborators (embedder, retriever, search, discoverer, seeder); ``_subagents`` builds the
remaining env-gated subagents (researcher, curator, critics, visual engine); ``_builders`` wires
them into the public pipelines. Only the builders are public — everything else is the root's
internal wiring.
"""

from ._builders import (
    build_agent_course_builder,
    build_live_prereq_builder,
    build_live_verifier,
    build_orchestrator,
)

__all__ = [
    "build_agent_course_builder",
    "build_live_prereq_builder",
    "build_live_verifier",
    "build_orchestrator",
]
