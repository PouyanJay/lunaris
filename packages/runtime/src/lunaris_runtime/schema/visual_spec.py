"""Typed, bounded visual specifications — the branded-renderer contract.

A ``VisualSpec`` is a safe, structured description of a diagram the web renders with its own
components; the agent emits one of these variants via structured output (never free-form markup or
code). Each variant is a ``CourseModel`` (camelCase wire, ``extra="forbid"``) discriminated by
``type``. Carried on ``Visual.spec``; ``Visual.source`` (Mermaid) remains the fallback.
"""

from typing import Annotated, Literal

from pydantic import Field

from .base import CourseModel

# ── flow: a directed node-graph (rendered on a movable canvas) ──────────────────


class FlowNode(CourseModel):
    id: str
    label: str


class FlowEdge(CourseModel):
    from_: str = Field(alias="from")
    to: str
    label: str | None = None


class FlowSpec(CourseModel):
    type: Literal["flow"] = "flow"
    title: str | None = None
    nodes: list[FlowNode] = Field(default_factory=list)
    edges: list[FlowEdge] = Field(default_factory=list)


# ── tree: a hierarchy, flattened (each node names its parent) ────────────────────


class TreeNode(CourseModel):
    id: str
    label: str
    parent_id: str | None = None  # None => a root


class TreeSpec(CourseModel):
    type: Literal["tree"] = "tree"
    title: str | None = None
    nodes: list[TreeNode] = Field(default_factory=list)


# ── steps: an ordered process ───────────────────────────────────────────────────


class StepItem(CourseModel):
    title: str
    detail: str | None = None


class StepsSpec(CourseModel):
    type: Literal["steps"] = "steps"
    title: str | None = None
    steps: list[StepItem] = Field(default_factory=list)


# ── comparison: a labelled table ────────────────────────────────────────────────


class ComparisonRow(CourseModel):
    label: str
    values: list[str] = Field(default_factory=list)


class ComparisonSpec(CourseModel):
    type: Literal["comparison"] = "comparison"
    title: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[ComparisonRow] = Field(default_factory=list)


# ── timeline: ordered events ─────────────────────────────────────────────────────


class TimelineEvent(CourseModel):
    label: str
    detail: str | None = None
    when: str | None = None


class TimelineSpec(CourseModel):
    type: Literal["timeline"] = "timeline"
    title: str | None = None
    events: list[TimelineEvent] = Field(default_factory=list)


# ── before-after: an interactive transformation (toggle between two states) ──────


class TransformSide(CourseModel):
    label: str
    content: str


class BeforeAfterSpec(CourseModel):
    type: Literal["before-after"] = "before-after"
    title: str | None = None
    # Both sides are required — a transformation with a missing state is half-formed, so the union
    # rejects it (the agent can't ship a broken before-after).
    before: TransformSide
    after: TransformSide


# A type alias, not a class — for runtime checks switch on `.type` (or isinstance against the
# concrete variants), never `isinstance(spec, VisualSpec)`.
VisualSpec = Annotated[
    FlowSpec | TreeSpec | StepsSpec | ComparisonSpec | TimelineSpec | BeforeAfterSpec,
    Field(discriminator="type"),
]
