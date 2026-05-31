"""The VisualSpec discriminated union — the branded-renderer contract carried on Visual.spec.

These lock the camelCase wire shape the web renderer consumes and prove the discriminator + the
``extra="forbid"`` safety gate (a spec is a bounded, typed structure, never free-form payload)."""

import pytest
from lunaris_runtime.schema import (
    ComparisonSpec,
    FlowSpec,
    StepsSpec,
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
