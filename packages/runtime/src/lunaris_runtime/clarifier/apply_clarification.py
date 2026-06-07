"""Merge a learner's confirmed :class:`Clarification` onto the inferred :class:`CourseBrief` (P7.5).

Pure: the goal interpreter infers the brief; this folds in the learner's confirm answers so the
build designs from the *calibrated* brief. Absent fields keep the inference, so an empty
``Clarification`` (or ``None``) is the identity — the zero-friction default == today's inferred-only
build. The diagnostic needs no separate frontier path: a richer ``assumed_prior`` + a confirmed
``target_level`` flow through the existing learner profiler (which reads both) into a sharper edge.
"""

from lunaris_runtime.schema import Clarification, CourseBrief, Preferences


def apply_clarification(brief: CourseBrief, clarification: Clarification | None) -> CourseBrief:
    """Return ``brief`` calibrated by ``clarification`` (a new brief; the input is untouched).

    ``None`` or an all-default clarification returns the brief unchanged, so callers can pass the
    learner's optional answers unconditionally and the skip path stays byte-for-byte today's build.
    """
    if clarification is None:
        return brief

    updates: dict[str, object] = {}
    if clarification.goal_type is not None:
        updates["goal_type"] = clarification.goal_type
    if clarification.target_level is not None:
        updates["target_level"] = clarification.target_level

    assumed_prior = _append_note(
        brief.assumed_prior, clarification.assumed_known, "The learner reports already knowing: {}."
    )
    if assumed_prior != brief.assumed_prior:
        updates["assumed_prior"] = assumed_prior

    audience = _append_note(brief.audience, clarification.background, "Learner background: {}.")
    if audience != brief.audience:
        updates["audience"] = audience

    preferences = _merge_preferences(brief.preferences, clarification)
    if preferences != brief.preferences:
        updates["preferences"] = preferences

    return brief.model_copy(update=updates) if updates else brief


def _append_note(base: str, value: str, template: str) -> str:
    value = value.strip()
    if not value:
        return base
    note = template.format(value)
    return f"{base} {note}".strip() if base else note


def _merge_preferences(preferences: Preferences, clarification: Clarification) -> Preferences:
    """Override only the preference axes the learner answered; keep the inference for the rest."""
    updates: dict[str, object] = {}
    if clarification.detail_depth is not None:
        updates["detail_depth"] = clarification.detail_depth
    if clarification.language_style is not None:
        updates["language_style"] = clarification.language_style
    return preferences.model_copy(update=updates) if updates else preferences
