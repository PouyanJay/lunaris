"""Curate per-lesson learning resources as a tool the agent calls (over ``IResourceCurator``).

After the lessons are authored + verified, enrich them: for each module the curator finds + vets
external resources (video / article / docs / practice / …) and assigns each to the Merrill phase it
best supports. The LLM-heavy discovery (search → trust-classify → fetch → judge) stays in the
curator subagent (live or a stub); this wires it, attaches the accepted resources onto the lesson
segments, emits ``RESOURCES_CURATED`` (plus a per-module reasoning beat so the otherwise-opaque step
streams), and returns a compact summary for the agent + the live resource-vetting card. Best-effort:
resources are suggested aids, so a module that yields none simply keeps its verified lesson.
"""

from dataclasses import fields

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import AgentEventKind, MerrillSegments, ProgressStage

from ...subagents.resource_curator import (
    CuratedResources,
    IResourceCurator,
    representative_modality,
)
from ..draft import CourseDraft


def _attach(lesson_segments: MerrillSegments, curated: CuratedResources) -> int:
    """Attach each phase's curated resources onto the matching Merrill segment; return the count.

    ``CuratedResources`` mirrors ``MerrillSegments`` field-for-field (the four phase names), so we
    iterate its dataclass fields rather than repeat the phase tuple that already lives elsewhere.
    """
    attached = 0
    for field in fields(curated):
        resources = getattr(curated, field.name)
        getattr(lesson_segments, field.name).resources = list(resources)
        attached += len(resources)
    return attached


async def _curate_all_modules(
    curator: IResourceCurator, draft: CourseDraft
) -> tuple[int, list[dict[str, object]]]:
    """Curate + attach resources for every authored module; return the total + per-module summary.

    Resolves each module's representative ``modality`` from the graph (CQ Phase 2) so the curator
    can shape its searches, skips modules with no authored lesson, and emits a per-module beat.
    """
    total = 0
    per_module: list[dict[str, object]] = []
    gaps: list[str] = []
    for module in draft.modules:
        if not module.lessons:
            continue
        modality = representative_modality(module, draft.graph)
        curated = await curator.curate(module, draft.brief, modality=modality)
        count = _attach(module.lessons[0].segments, curated)
        total += count
        per_module.append({"id": module.id, "title": module.title, "resourceCount": count})
        if count == 0:
            # No silent zero (T5): record the gap + say so, rather than shipping an empty module.
            gaps.append(module.title)
            await draft.agent.emit(
                AgentEventKind.REASONING,
                text=f"No suitable resources found for “{module.title}” — it ships without aids.",
            )
        else:
            await draft.agent.emit(
                AgentEventKind.REASONING,
                text=f"Curated {count} resource(s) for “{module.title}”.",
            )
    draft.resource_coverage_gaps = gaps
    return total, per_module


def make_curate_resources_tool(curator: IResourceCurator, draft: CourseDraft) -> BaseTool:
    """Build the ``curate_resources`` tool, closed over the curator and the run draft.

    Iterates the authored modules, curates resources per module, and attaches them to that lesson's
    segments on the draft (read back by ``finalize_course``). Skips a module with no authored
    lesson, and degrades to zero resources without failing when curation finds nothing.
    """

    @tool
    async def curate_resources() -> dict[str, object]:
        """Attach vetted external learning resources to each authored lesson.

        Call this AFTER the module-author subagent has authored + verified the lessons, and BEFORE
        finalize_course. For each module it searches, vets (quality + trust + level-match), and
        attaches the best resources to the most relevant lesson phase; the resources are recorded on
        the draft automatically — you do NOT pass them back. Returns a per-module count summary.
        """
        total, per_module = await _curate_all_modules(curator, draft)
        await draft.progress.emit(
            ProgressStage.RESOURCES_CURATED,
            f"Curated {total} learning resource(s) across {len(per_module)} module(s)",
            module_count=len(per_module),
        )
        return {"resourceCount": total, "moduleCount": len(per_module), "modules": per_module}

    return curate_resources
