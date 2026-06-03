import re
from enum import StrEnum

import structlog
from lunaris_runtime.schema import (
    CourseBrief,
    DeliverableShape,
    DetailDepth,
    LanguageStyle,
    Level,
    Preferences,
    StandardKind,
    TargetStandard,
)

from ..json_tolerant import loads_tolerant

logger = structlog.get_logger()

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _coerce_enum[E: StrEnum](value: object, enum_cls: type[E], default: E) -> E:
    """Map a model string to an enum member, defaulting on any mismatch."""
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return default


def _target_standard(raw: object) -> TargetStandard | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    return TargetStandard(
        name=name,
        kind=_coerce_enum(raw.get("kind"), StandardKind, StandardKind.EXTERNAL_STANDARD),
        authority_hint=str(raw.get("authority_hint", "")),
    )


def _deliverable_shape(raw: object) -> DeliverableShape:
    if not isinstance(raw, dict):
        return DeliverableShape()
    lessons = raw.get("lessons")
    if lessons is None:
        return DeliverableShape()
    try:
        count = int(lessons)
    except (TypeError, ValueError):
        return DeliverableShape()
    # A non-positive count is not a real constraint — collapse it to "unconstrained".
    return DeliverableShape(lessons=count if count > 0 else None)


def _preferences(raw: object) -> Preferences:
    if not isinstance(raw, dict):
        return Preferences()
    return Preferences(
        detail_depth=_coerce_enum(raw.get("detail_depth"), DetailDepth, DetailDepth.BALANCED),
        language_style=_coerce_enum(
            raw.get("language_style"), LanguageStyle, LanguageStyle.BALANCED
        ),
    )


def _subject_goal(data: dict[str, object]) -> tuple[str, str]:
    """The subject + goal, each backfilled from the other so later stages always have both."""
    subject = str(data.get("subject", "")).strip()
    goal = str(data.get("goal", "")).strip()
    if not subject and not goal:
        raise ValueError("interpreter returned neither a subject nor a goal")
    if not subject or not goal:
        # The model gave only one — usually a sign the request was under-specified; log it so the
        # gap is observable (mirrors the extractor's goal-id fallback warning), then backfill.
        logger.warning("interpreter_backfilled_subject_or_goal", subject=subject, goal=goal)
    return subject or goal, goal or subject


def parse_brief(text: str) -> CourseBrief:
    """Parse the interpreter's JSON into a validated ``CourseBrief``.

    Tolerant of prose/code-fences around the JSON and of individual malformed fields (each defaults
    rather than crashing the build) — strict only that the response carries a subject or a goal.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in interpreter response")
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("interpreter response is not a JSON object")

    subject, goal = _subject_goal(data)
    return CourseBrief(
        subject=subject,
        goal=goal,
        target_standard=_target_standard(data.get("target_standard")),
        target_level=_coerce_enum(data.get("target_level"), Level, Level.NOT_APPLICABLE),
        assumed_prior=str(data.get("assumed_prior", "")),
        audience=str(data.get("audience", "")),
        deliverable_shape=_deliverable_shape(data.get("deliverable_shape")),
        needs_research=bool(data.get("needs_research", False)),
        domain_field=str(data.get("domain_field", "")),
        preferences=_preferences(data.get("preferences")),
    )
