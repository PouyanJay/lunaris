from itertools import pairwise

from lunaris_runtime.schema import (
    Assessment,
    Item,
    Module,
    Objective,
    PrerequisiteGraph,
)

from .plan import CurriculumPlan


class CurriculumAssembler:
    """Turns a CurriculumPlan into validated course-object ``Module``s.

    Deterministic: assigns item ids, links objectives↔items, computes each module's
    difficulty index from its KCs, and enforces the backward-design invariants
    (every objective assessed; difficulty non-decreasing across modules).
    """

    def assemble(self, plan: CurriculumPlan, graph: PrerequisiteGraph) -> list[Module]:
        difficulty = {kc.id: kc.difficulty for kc in graph.nodes}
        modules: list[Module] = []

        for m_index, module_plan in enumerate(plan.modules):
            objectives: list[Objective] = []
            items: list[Item] = []
            for o_index, obj in enumerate(module_plan.objectives):
                item_ids: list[str] = []
                for i_index, prompt in enumerate(obj.item_prompts):
                    item_id = f"m{m_index}-o{o_index}-i{i_index}"
                    items.append(Item(id=item_id, prompt=prompt, objective=obj.kc))
                    item_ids.append(item_id)
                if not item_ids:
                    raise ValueError(f"objective for KC {obj.kc!r} has no items")
                objectives.append(
                    Objective(
                        statement=obj.statement,
                        bloom_level=obj.bloom_level,
                        kc=obj.kc,
                        assessed_by=item_ids,
                    )
                )

            module_kcs = module_plan.kcs or [o.kc for o in module_plan.objectives]
            covered = [difficulty[k] for k in module_kcs if k in difficulty]
            difficulty_index = max(covered) if covered else 0.0

            modules.append(
                Module(
                    id=f"m{m_index}",
                    title=module_plan.title,
                    kcs=module_kcs,
                    objectives=objectives,
                    assessment=Assessment(items=items),
                    difficulty_index=difficulty_index,
                )
            )

        self._assert_difficulty_monotonic(modules)
        return modules

    def _assert_difficulty_monotonic(self, modules: list[Module]) -> None:
        for earlier, later in pairwise(modules):
            if later.difficulty_index < earlier.difficulty_index:
                raise ValueError(
                    "module difficulty is not non-decreasing: "
                    f"{earlier.id}={earlier.difficulty_index} > {later.id}={later.difficulty_index}"
                )
