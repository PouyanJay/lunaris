"""Structure-derives-from-research coverage (CQ Phase 1.3).

A deterministic check that the curriculum's structure was built backward from the researched
competency framework rather than invented: a researched competency is *covered* when some module is
tagged with it (the ``competency`` field the architect maps each module to). Surfaced as a build
signal (logged by ``design_curriculum``); the full coverage *critic* that forces a fix is Phase 4.
"""

from collections.abc import Sequence

from lunaris_runtime.schema import Module, StandardResearch


def framework_coverage(
    research: StandardResearch, modules: Sequence[Module]
) -> tuple[list[str], list[str]]:
    """Split the researched competencies into (covered, uncovered) by the modules' competency tags.

    A competency is covered when a module's ``competency`` field equals it verbatim — the structural
    record (P7.3) that the module was designed backward from that part of the standard. Order
    follows ``research.competencies`` so the result is stable.
    """
    tagged = {module.competency for module in modules if module.competency}
    covered = [competency for competency in research.competencies if competency in tagged]
    uncovered = [competency for competency in research.competencies if competency not in tagged]
    return covered, uncovered
