"""What a compiled map has to be true of, stated once so ten topics are judged the same way.

Phase 1's exit criterion ends in a human: "graphs a domain-literate reviewer accepts". Nothing here
replaces that judgement — a machine cannot tell whether *supply* really precedes *equilibrium*. What
it can do is refuse to waste the reviewer's attention on maps that are already broken on their face,
and hand over a digest they can actually read.

So this is a floor, not a verdict. It catches structural lies (a prerequisite that does not exist, a
dependency taught before what it depends on), and the substance failures the schema deliberately
permits so that one bad model call cannot condemn a whole compile: a node with no teaching spec, a
mastery criterion phrased as knowing rather than doing, a map with no aliases for a learner's
wording to land on.

Complaints are returned rather than asserted, so one run reports everything wrong with a map instead
of stopping at the first thing — ten topics at three minutes each is too expensive to bisect.
"""

from lunaris_live.graph import ConceptGraph, NodeProvenance

#: The band a whole-topic map should land in (requirements, Open question 1: target 12-20). Checked
#: wider than the target because the target is a *budget* and this is a floor: eleven concepts is a
#: judgement call for the reviewer, five is a map that decomposition gave up on, and forty is one
#: that will not fit the three-minute budget on any slower model.
_MIN_NODES = 8
_MAX_NODES = 30

#: How much of a map may be missing its teaching spec before the map itself is the problem. The
#: compiler keeps a concept whose authoring call failed rather than dropping it (a real concept
#: badly served beats a hole in the map), so a couple is a bad minute at the provider — but a
#: quarter of them means the authoring prompt, not the weather.
_MAX_UNSPECIFIED_SHARE = 0.2

#: Openings that make a mastery criterion unwatchable. The schema's whole claim is that a criterion
#: is something the learner can be seen to DO; "knows that gradients point uphill" cannot be staged,
#: scored, or failed, and a phase that generates checks from these would generate nothing.
_KNOWLEDGE_OPENERS = (
    "know ",
    "knows ",
    "knowing ",
    "understand ",
    "understands ",
    "understanding ",
    "be aware",
    "is aware",
    "appreciate ",
    "be familiar",
    "is familiar",
    "remember that",
    "learn about",
)


def complaints_about(graph: ConceptGraph) -> list[str]:
    """Everything wrong with ``graph`` that a machine can be sure about. Empty means "worth a
    reviewer's time", never "correct"."""
    return [
        *_structural_complaints(graph),
        *_substance_complaints(graph),
    ]


def _structural_complaints(graph: ConceptGraph) -> list[str]:
    """Claims assembly is supposed to guarantee — re-checked here because this is the only place
    assembly ever sees real model output rather than a fixture."""
    complaints: list[str] = []
    ids = {node.id for node in graph.nodes}

    if not graph.is_acyclic:
        complaints.append("the map is not acyclic")
    if set(graph.topo_order) != ids:
        missing = sorted(ids - set(graph.topo_order))
        extra = sorted(set(graph.topo_order) - ids)
        complaints.append(f"topo_order does not cover the nodes (missing={missing}, extra={extra})")
    if len(graph.topo_order) != len(set(graph.topo_order)):
        complaints.append("topo_order repeats a concept")

    position = {node_id: index for index, node_id in enumerate(graph.topo_order)}
    for node in graph.nodes:
        for required in node.requires:
            if required not in ids:
                complaints.append(f"{node.id} requires {required!r}, which is not on the map")
            elif position.get(required, -1) > position.get(node.id, -1):
                complaints.append(f"{node.id} is taught before its prerequisite {required}")
    return complaints


def _substance_complaints(graph: ConceptGraph) -> list[str]:
    """What makes the map teachable rather than merely well-formed."""
    complaints: list[str] = []

    if not _MIN_NODES <= len(graph.nodes) <= _MAX_NODES:
        complaints.append(
            f"{len(graph.nodes)} concepts is outside the {_MIN_NODES}-{_MAX_NODES} band"
        )

    unspecified = [node.id for node in graph.nodes if node.teaching_spec is None]
    if graph.nodes and len(unspecified) > _MAX_UNSPECIFIED_SHARE * len(graph.nodes):
        complaints.append(
            f"{len(unspecified)}/{len(graph.nodes)} concepts have no teaching spec: {unspecified}"
        )

    if graph.nodes and not any(node.aliases for node in graph.nodes):
        # C2 matches a learner's wording against names *and* aliases. A map with none is one where
        # every question has to be asked in the compiler's vocabulary.
        complaints.append("no concept has an alias, so C2 can only match the compiler's own words")

    for node in graph.nodes:
        if node.provenance is not NodeProvenance.COMPILED:
            complaints.append(f"{node.id} is marked {node.provenance} on a cold compile")
        if node.definition.strip().lower() == node.name.strip().lower():
            complaints.append(f"{node.id} restates its name instead of defining it")
        if node.teaching_spec is None:
            continue
        if not node.teaching_spec.misconceptions:
            complaints.append(f"{node.id} has no misconceptions, which is the field a tutor hunts")
        if not node.mastery_criteria:
            complaints.append(
                f"{node.id} has no mastery criteria, so nothing about it is checkable"
            )
        for criterion in node.mastery_criteria:
            if _is_knowledge_claim(criterion.statement):
                complaints.append(
                    f"{node.id} states mastery as knowing, not doing: {criterion.statement!r}"
                )
    return complaints


def _is_knowledge_claim(statement: str) -> bool:
    """Whether a criterion is phrased as knowing rather than doing. Leading verb only — "explain
    what a prior is and why knowing it matters" is a do-statement with the word in it."""
    return statement.strip().lower().startswith(_KNOWLEDGE_OPENERS)


def digest(graph: ConceptGraph, *, elapsed_s: float) -> str:
    """The map as something a domain-literate reviewer can read in a minute.

    Written in the graph's own teaching order with prerequisites named rather than id-referenced,
    because the question being asked of it is "would you teach it in this order", and nobody can
    answer that against a list of ids.
    """
    names = {node.id: node.name for node in graph.nodes}
    by_id = {node.id: node for node in graph.nodes}
    lines = [
        f"# {graph.topic}",
        "",
        f"`{len(graph.nodes)}` concepts · compiled in `{elapsed_s:.1f}s` · "
        f"acyclic: `{graph.is_acyclic}` · version `{graph.version}`",
        "",
        "> Read in teaching order. The question is whether these are the right concepts, in an "
        "order you would actually teach, with nothing invented.",
        "",
    ]
    for position, node_id in enumerate(graph.topo_order, start=1):
        node = by_id[node_id]
        needs = ", ".join(names.get(r, r) for r in node.requires) or "—"
        lines += [
            f"## {position}. {node.name}",
            "",
            node.definition,
            "",
            f"**Needs first:** {needs}",
        ]
        if node.aliases:
            lines.append(f"**Also called:** {', '.join(node.aliases)}")
        if node.teaching_spec is None:
            lines += ["", "_No teaching spec — authoring failed for this concept._", ""]
            continue
        lines += ["", f"**Objective ({node.teaching_spec.depth}):** {node.teaching_spec.objective}"]
        if node.teaching_spec.misconceptions:
            lines.append("**Learners wrongly believe:**")
            lines += [f"- {m}" for m in node.teaching_spec.misconceptions]
        if node.mastery_criteria:
            lines.append("**Can do:**")
            lines += [
                f"- _{c.kind}_ — {c.statement}" + (" (needs a sim)" if c.needs_sim else "")
                for c in node.mastery_criteria
            ]
        lines.append("")
    return "\n".join(lines) + "\n"
