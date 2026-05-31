"""Concept-extraction as a tool the agent calls (thin adapter over ``IConceptExtractor``).

The LLM-heavy work (proposing knowledge components for a topic) stays in the existing extractor
subagent (live Claude or a stub); this wraps it as a capability tool, records the typed result in
the run draft, and returns a compact summary the agent uses to drive the next step (the graph tool).
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ...subagents.concept_extractor import IConceptExtractor
from ..draft import CourseDraft


def make_extract_concepts_tool(extractor: IConceptExtractor, draft: CourseDraft) -> BaseTool:
    """Build the ``extract_concepts`` tool, closed over the extractor and the run draft.

    The tool records the extracted concepts + goal on ``draft`` (authoritative typed data) and
    returns a compact summary for the agent to reason over and pass to the graph tool.
    """

    @tool
    async def extract_concepts(topic: str) -> dict[str, object]:
        """Propose the knowledge components (concepts) a course on ``topic`` must teach.

        Returns ``{goalId, count, concepts: [{id, label, definition, difficulty}]}``. Feed the
        returned concepts into ``build_prerequisite_graph`` to get the authoritative teaching order.
        """
        extraction = await extractor.extract(topic)
        draft.goal_concept = extraction.goal_id
        draft.concepts = list(extraction.kcs)
        await draft.progress.emit(
            ProgressStage.CONCEPTS_EXTRACTED,
            f"Extracted {len(extraction.kcs)} concepts",
            kc_count=len(extraction.kcs),
        )
        return {
            "goalId": extraction.goal_id,
            "count": len(extraction.kcs),
            "concepts": [
                {
                    "id": kc.id,
                    "label": kc.label,
                    "definition": kc.definition,
                    "difficulty": kc.difficulty,
                }
                for kc in extraction.kcs
            ],
        }

    return extract_concepts
