from lunaris_runtime.schema import CourseBrief, Level

# Levels above a true novice: extraction scopes to the GAP (the competencies that define reaching
# the goal), not the whole ladder. NOVICE / NOT_APPLICABLE keep the full-ladder novice behavior.
_SCOPED_LEVELS = frozenset({Level.INTERMEDIATE, Level.ADVANCED, Level.EXPERT})

# The shared response shape both prompts end with — one authoritative copy of the KC JSON schema.
_KC_JSON_RESPONSE_SHAPE = (
    "Respond with ONLY this JSON, no prose:\n"
    '{"goal_id": "<id>", "kcs": [{"id": "...", "label": "...", "definition": "...",\n'
    '"difficulty": 0.0, "bloom_ceiling": "apply"}]}'
)

_NOVICE_PROMPT = """Decompose a learning topic into its atomic knowledge components (KCs).

Topic: "{topic}"

A knowledge component is the smallest unit teachable in one sitting. List every KC a
learner must master to reach the topic, INCLUDING the foundational prerequisites they
likely need first. For each KC give:
  - id: short snake_case identifier
  - label: a human-readable name
  - definition: one sentence
  - difficulty: 0.0 (most basic) to 1.0 (the topic itself)
  - bloom_ceiling: one of remember, understand, apply, analyze, evaluate, create

The single most advanced KC — the topic itself — is the goal."""

_GAP_PROMPT = """Decompose a learning GOAL into the knowledge components (KCs) that DEFINE reaching
it for a learner ALREADY at the stated level — the GAP, not the whole ladder.

Subject: "{subject}"
Goal: "{goal}"
Target level: {level}
Assume the learner already has: {assumed_prior}
The learner already knows these — do NOT teach them or anything beneath them: {frontier}

List ONLY the KCs that distinguish a {level} learner from that prior knowledge — the competencies
that define reaching the goal. Do NOT include foundational prerequisites the learner already has;
start at their edge (Vygotsky's ZPD). For each KC give:
  - id: short snake_case identifier
  - label: a human-readable name
  - definition: one sentence
  - difficulty: 0.0 (easiest of the gap) to 1.0 (the goal itself)
  - bloom_ceiling: one of remember, understand, apply, analyze, evaluate, create

The single most advanced KC — the goal itself — is the goal."""


def build_extraction_prompt(topic: str, brief: CourseBrief | None, frontier: list[str]) -> str:
    """The extraction prompt: gap-scoped when the brief sets a non-novice level, else the full
    novice ladder.

    Gap-scoping is the fix for the "advanced goal taught from the alphabet" failure: it tells the
    model to enumerate only the competencies that distinguish the target level from the learner's
    assumed prior, and to skip the foundations on the frontier.
    """
    if brief is not None and brief.target_level in _SCOPED_LEVELS:
        known = ", ".join(frontier) if frontier else "the general foundations for this level"
        body = _GAP_PROMPT.format(
            subject=brief.subject,
            goal=brief.goal,
            level=brief.target_level.value,
            assumed_prior=brief.assumed_prior or "the foundations beneath the target level",
            frontier=known,
        )
    else:
        body = _NOVICE_PROMPT.format(topic=topic)
    return f"{body}\n\n{_KC_JSON_RESPONSE_SHAPE}"
