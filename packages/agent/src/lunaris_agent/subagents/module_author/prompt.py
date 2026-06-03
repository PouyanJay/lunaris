from lunaris_runtime.schema import CourseBrief, DetailDepth, LanguageStyle, Module

# How the brief's preferences read in the prompt — the requested register + depth steer the voice
# (plan §5A: preferences set at interpret time steer authoring). BALANCED needs no instruction.
_REGISTER_PHRASE: dict[LanguageStyle, str] = {
    LanguageStyle.SIMPLE: "simple, plain-language",
    LanguageStyle.SOPHISTICATED: "sophisticated",
    LanguageStyle.SCIENTIFIC: "scientific, technical",
}
_DEPTH_PHRASE: dict[DetailDepth, str] = {
    DetailDepth.CONCISE: "concise",
    DetailDepth.IN_DEPTH: "in-depth",
}

_HEADER = (
    "Author one lesson for a course module as a complete learning ARC "
    "(Merrill's First Principles).\n\n"
    'Module: "{title}"'
)

# The arc rhythm a great human tutor uses, mapped onto the four Merrill phases plus the two bookends
# the cycle lacks (P7.3): the lesson shape the competency is taught through, not a difficulty climb.
_ARC_BODY = """Write the lesson as an arc that mirrors the competency, not a generic climb:
- expects: 2-4 short bullets naming what the learner should ALREADY be comfortable with before this
  lesson (entry expectations). Do NOT teach these — they set the starting line.
- activate: connect to prior knowledge or a relatable real-world problem.
- demonstrate: the core teaching — explain the STRATEGY and show a concrete WORKED EXAMPLE.
- apply: a guided PRACTICE step the learner does.
- integrate: how the learner transfers this to their own context.
- self_check: 2-4 short SELF-CHECK prompts the learner runs to confirm they reached the competency.

For each of the four phases write concise prose, and list every factual sentence (a claim that could
be fact-checked) separately in "claims" so it can be verified. expects and self_check are short
scaffolding lines the learner reads, NOT factual claims — leave claims out of them."""

_JSON_SHAPE = """Respond with ONLY this JSON, no prose:
{"expects": ["..."],
 "activate": {"prose": "...", "claims": ["..."]},
 "demonstrate": {"prose": "...", "claims": ["..."]},
 "apply": {"prose": "...", "claims": ["..."]},
 "integrate": {"prose": "...", "claims": ["..."]},
 "self_check": ["..."]}"""


def _voice_line(brief: CourseBrief) -> str:
    register = _REGISTER_PHRASE.get(brief.preferences.language_style)
    depth = _DEPTH_PHRASE.get(brief.preferences.detail_depth)
    if register and depth:
        return f"Write in a {register} register, with {depth} detail."
    if register:
        return f"Write in a {register} register."
    if depth:
        return f"Write with {depth} detail."
    return ""


def _frontier_line(frontier: list[str]) -> str:
    known = ", ".join(frontier)
    return (
        "The learner already knows these — pitch 'expects' at that edge, do not re-teach them "
        f"or anything beneath them: {known}"
    )


def _revision_note(cut_claims: list[str]) -> str:
    listed = "\n".join(f"- {claim}" for claim in cut_claims)
    return (
        "These factual claims could not be grounded against the evidence corpus and were CUT:\n"
        f"{listed}\nRe-author the lesson so each cut claim is restated as a verifiable, "
        "well-known fact or replaced with one. Keep the arc — expects, the four phases, and "
        "self_check — intact."
    )


def build_authoring_prompt(
    module: Module,
    *,
    brief: CourseBrief | None = None,
    frontier: list[str] | None = None,
    cut_claims: list[str] | None = None,
) -> str:
    """The lesson-authoring prompt: a personalized arc (expects → strategies → worked example →
    practice → self-check) that mirrors the standard's competency, not a generic climb (P7.3).

    Personalization comes from the brief and the module: the module's researched ``competency`` aims
    the whole arc; ``brief.target_level`` + subject/goal pitch it; the ``frontier`` sets where
    ``expects`` sits (so foundations beneath the learner's edge are not re-taught); and
    ``brief.preferences`` steer the register + depth. Without a brief it degrades to a generic arc
    (the legacy / novice path). With ``cut_claims`` a revision note is folded in so the author
    re-grounds them while keeping the arc intact.
    """
    sections = [_HEADER.format(title=module.title)]

    if module.competency:
        sections.append(
            f"This lesson builds toward the competency: {module.competency}. Aim the whole arc at "
            "earning it."
        )
    if brief is not None:
        sections.append(
            f"Subject: {brief.subject}\nGoal: {brief.goal}\n"
            f"Target level: {brief.target_level.value}"
        )

    objectives = "\n".join(f"- {objective.statement}" for objective in module.objectives)
    sections.append(f"Learning objectives:\n{objectives}")
    sections.append(_ARC_BODY)

    if frontier:
        sections.append(_frontier_line(frontier))
    if brief is not None and (voice := _voice_line(brief)):
        sections.append(voice)
    if cut_claims:
        sections.append(_revision_note(cut_claims))

    sections.append(_JSON_SHAPE)
    return "\n\n".join(sections)
