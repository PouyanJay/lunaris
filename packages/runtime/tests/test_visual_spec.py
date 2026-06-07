"""The VisualSpec discriminated union — the branded-renderer contract carried on Visual.spec.

These lock the camelCase wire shape the web renderer consumes and prove the discriminator + the
``extra="forbid"`` safety gate (a spec is a bounded, typed structure, never free-form payload)."""

import pytest
from lunaris_runtime.schema import (
    ComparisonSpec,
    FlowSpec,
    StepsSpec,
    TransformSide,
    TreeNode,
    TreeSpec,
    Visual,
    VisualKind,
)
from pydantic import ValidationError


def test_flow_spec_serializes_camelcase_on_a_visual() -> None:
    # Arrange
    visual = Visual(
        kind=VisualKind.MERMAID,
        source="graph TD",
        spec=FlowSpec(
            title="Search",
            nodes=[{"id": "a", "label": "Start"}, {"id": "b", "label": "End"}],
            edges=[{"from": "a", "to": "b", "label": "next"}],
        ),
    )

    # Act
    wire = visual.model_dump(by_alias=True)

    # Assert — the discriminator + the edge's `from` alias survive to the wire.
    spec = wire["spec"]
    assert spec["type"] == "flow"
    assert spec["nodes"][0] == {"id": "a", "label": "Start"}
    assert spec["edges"][0]["from"] == "a"
    assert spec["edges"][0]["to"] == "b"
    assert spec["edges"][0]["label"] == "next"


def test_visual_round_trips_through_the_wire() -> None:
    # Arrange
    original = Visual(kind=VisualKind.MERMAID, source="x", spec=StepsSpec(steps=[{"title": "One"}]))

    # Act
    restored = Visual.model_validate(original.model_dump(by_alias=True))

    # Assert
    assert isinstance(restored.spec, StepsSpec)
    assert restored.spec.type == "steps"
    assert restored.spec.steps[0].title == "One"


def test_spec_discriminator_selects_the_variant() -> None:
    # Act — a raw camelCase comparison spec, the way it arrives over the wire.
    visual = Visual.model_validate(
        {
            "kind": "mermaid",
            "source": "x",
            "spec": {
                "type": "comparison",
                "columns": ["A", "B"],
                "rows": [{"label": "r", "values": ["1", "2"]}],
            },
        }
    )

    # Assert — the comparison variant is selected from the raw `type` discriminator.
    assert isinstance(visual.spec, ComparisonSpec)
    assert visual.spec.columns == ["A", "B"]
    assert visual.spec.rows[0].values == ["1", "2"]


def test_tree_spec_serializes_parent_id_as_camelcase() -> None:
    # Arrange — parentId is the only multi-word field the web mirror reads via the alias generator.
    spec = TreeSpec(nodes=[TreeNode(id="child", label="Child", parent_id="root")])

    # Act
    restored = TreeSpec.model_validate(spec.model_dump(by_alias=True))

    # Assert — it serializes camelCase and round-trips back.
    assert spec.model_dump(by_alias=True)["nodes"][0]["parentId"] == "root"
    assert restored.nodes[0].parent_id == "root"


def test_before_after_spec_round_trips_through_the_wire() -> None:
    # Act — a raw camelCase before-after spec, the way it arrives over the wire (the interactive
    # transformation variant: two labelled sides the reader toggles between).
    visual = Visual.model_validate(
        {
            "kind": "spec",
            "source": "",
            "spec": {
                "type": "before-after",
                "title": "From linear to binary search",
                "before": {"label": "Before", "content": "scan every element"},
                "after": {"label": "After", "content": "halve the search space"},
            },
        }
    )

    # Assert — the discriminator selects the variant and the two sides survive.
    assert visual.spec is not None
    assert visual.spec.type == "before-after"
    assert visual.spec.before.label == "Before"
    assert visual.spec.after.content == "halve the search space"

    # And it round-trips back through the camelCase wire unchanged.
    restored = Visual.model_validate(visual.model_dump(by_alias=True))
    assert restored.spec is not None
    assert restored.spec.type == "before-after"
    assert restored.spec.after.label == "After"


def test_before_after_side_carries_optional_language_and_caption() -> None:
    # Act — a code-bearing side names its language (→ rendered as code) and a caption.
    visual = Visual.model_validate(
        {
            "kind": "spec",
            "source": "",
            "spec": {
                "type": "before-after",
                "before": {
                    "label": "Naive",
                    "content": "for x in xs: ...",
                    "language": "python",
                    "caption": "O(n) per lookup",
                },
                "after": {"label": "Binary search", "content": "lo, hi = 0, n"},
            },
        }
    )

    # Assert — the optional fields ride the side, and default to None when omitted.
    assert visual.spec is not None
    assert visual.spec.before.language == "python"
    assert visual.spec.before.caption == "O(n) per lookup"
    bare = TransformSide(label="x", content="y")
    assert bare.language is None
    assert bare.caption is None


def test_before_after_spec_requires_both_sides() -> None:
    # Act / Assert — a before-after missing the `after` side is invalid; the validator rejects it
    # rather than shipping a half-formed transformation.
    with pytest.raises(ValidationError):
        Visual.model_validate(
            {
                "kind": "spec",
                "source": "",
                "spec": {
                    "type": "before-after",
                    "before": {"label": "Before", "content": "x"},
                },
            }
        )


def test_worked_example_spec_round_trips_through_the_wire() -> None:
    # Act — a raw worked-example spec the way it arrives over the wire: a literal phrasing, an
    # improved rewrite, and the note that explains why the rewrite is better.
    visual = Visual.model_validate(
        {
            "kind": "spec",
            "source": "",
            "spec": {
                "type": "worked-example",
                "title": "Worked Example 1",
                "literal": {"label": "Literal", "content": "We will work very hard on this."},
                "improved": {
                    "label": "With collocation",
                    "content": "We will do the heavy lifting on this.",
                },
                "note": "'do the heavy lifting' suits a professional tone.",
            },
        }
    )

    # Assert — the discriminator selects the variant; both sides + the note survive.
    assert visual.spec is not None
    assert visual.spec.type == "worked-example"
    assert visual.spec.literal.content == "We will work very hard on this."
    assert visual.spec.improved.label == "With collocation"
    assert visual.spec.note == "'do the heavy lifting' suits a professional tone."

    # And it round-trips back through the camelCase wire unchanged.
    restored = Visual.model_validate(visual.model_dump(by_alias=True))
    assert restored.spec is not None
    assert restored.spec.type == "worked-example"
    assert restored.spec.improved.content == "We will do the heavy lifting on this."


def test_worked_example_spec_requires_both_sides() -> None:
    # Act / Assert — a worked example missing the improved side is half-formed; the validator
    # rejects it rather than shipping a one-sided example (the contrast is the point).
    with pytest.raises(ValidationError):
        Visual.model_validate(
            {
                "kind": "spec",
                "source": "",
                "spec": {
                    "type": "worked-example",
                    "literal": {"label": "Literal", "content": "x"},
                },
            }
        )


def test_spec_rejects_unknown_fields() -> None:
    # Act / Assert — extra="forbid" (on CourseModel) refuses unrecognised keys, not just any error.
    with pytest.raises(ValidationError) as exc_info:
        FlowSpec.model_validate({"type": "flow", "bogus": 1})

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


def test_visual_spec_defaults_to_none() -> None:
    # Arrange / Act — a visual without a spec (Mermaid-only) keeps spec null.
    visual = Visual(kind=VisualKind.MERMAID, source="x")

    # Assert
    assert visual.spec is None
    assert visual.model_dump(by_alias=True)["spec"] is None
