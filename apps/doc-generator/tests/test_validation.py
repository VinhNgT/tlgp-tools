"""Tests for validation logic."""

from pathlib import Path
import pytest
from doc_generator.models import (
    NodeSpec,
    ScreenSpec,
    Api,
    ApiParam,
    Interaction,
    ApiPayload,
)
from doc_generator.validation import validate_spec
from pydantic import ValidationError


def _minimal_spec(tmp_path, **overrides) -> ScreenSpec:
    nodes = overrides.pop("nodes", [])

    # Ensure exactly one screen component (id == "0") exists
    screen_comp = [n for n in nodes if n.id == "0"]
    if not screen_comp:
        (Path(tmp_path) / "screen.png").touch()
        nodes.append(
            NodeSpec(
                id="0",
                label="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                childrenIds=["1"],
                apis=[Api(api="GET Test", url="/test")],
                required=False,
                editable=False,
            )
        )
        nodes.append(
            NodeSpec(
                id="1",
                label="Test Child",
                controlType="Button",
                required=False,
                editable=False,
            )
        )
    else:
        # touch any defined image files to avoid validation issues
        for n in nodes:
            for img_file in n.imageFiles:
                if img_file:
                    (Path(tmp_path) / img_file).touch()

    defaults = {
        "sectionPrefix": "1.1",
        "imageDir": str(tmp_path),
        "nodes": nodes,
    }
    defaults.update(overrides)

    return ScreenSpec(**defaults)


class TestValidateSpec:
    def test_valid_spec(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()

        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1", "2"],
                    apis=[Api(api="GET Test", url="/test")],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=["3"],
                    interactions=[Interaction(action="Click", reaction="Test")],
                ),
                NodeSpec(
                    id="2",
                    label="Banner",
                    controlType="Image",
                    description="desc desc desc",
                ),
                NodeSpec(
                    id="3",
                    label="Button",
                    controlType="Button",
                    description="desc desc desc",
                ),
            ],
        )

        result = validate_spec(spec)
        assert result.valid is True
        assert not result.errors
        assert not result.warnings
        assert result.components == 2  # Screen + Comp 1
        assert result.non_leaf == 1    # Comp 1
        assert result.ui_elements == 3 # 2 (screen) + 1 (comp 1)
        assert result.images == 2
        assert result.apis == 1

    def test_missing_images(self, tmp_path):
        spec = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["missing_screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    imageFiles=["missing_comp.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
            ]
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert len(result.errors) == 2
        assert any("Screen image not found:" in err for err in result.errors)
        assert any("image not found:" in err for err in result.errors)

    def test_error_empty_description(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="",
                    imageFiles=["comp.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert any("empty description" in err for err in result.errors)

    def test_error_empty_children(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc",
                    imageFiles=["comp.png"],
                    childrenIds=[],
                )
            ],
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert any("no children specified" in err for err in result.errors)

    def test_error_empty_screen_description(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("Screen description is empty" in err for err in result.errors)

    def test_error_empty_screen_children(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc",
                    imageFiles=["screen.png"],
                    childrenIds=[],
                )
            ],
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("Screen has no children" in err for err in result.errors)

    def test_error_no_screen_images(self, tmp_path):
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc",
                    imageFiles=[],
                    childrenIds=["1"],
                    apis=[Api(api="GET Test", url="/test")],
                ),
                NodeSpec(
                    id="1",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert any("No screen-level images specified" in err for err in result.errors)

    def test_error_no_imageFiles_in_component(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc",
                    imageFiles=[],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert any("no imageFiles specified" in err for err in result.errors)

    def test_error_image_path_traversal(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        outside_file = Path(tmp_path).parent / "outside.png"
        outside_file.touch()

        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc",
                    imageFiles=["../outside.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("escapes imageDir" in e for e in result.errors)
        outside_file.unlink()

    def test_warnings_empty_labels(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label=" ",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["2"],
                    interactions=[Interaction(action="A", reaction="B")],
                ),
                NodeSpec(
                    id="2",
                    label=" ",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("empty label" in w for w in result.warnings)

    def test_warning_orphan_component(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="1",
                    label="Orphan Component",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=["3"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
                NodeSpec(
                    id="3",
                    label="Orphan Element",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("never referenced in the tree hierarchy" in w for w in result.warnings)

    def test_warnings_short_description(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="short",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Test",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("suspiciously short" in w for w in result.warnings)

    def test_warnings_empty_api_param(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            api="GET Test",
                            url="/test",
                            request=[
                                ApiPayload(
                                    type="TestDto",
                                    fields=[
                                        ApiParam(name=" ", meaning="valid", dataType="String")
                                    ]
                                )
                            ],
                        )
                    ],
                ),
                NodeSpec(
                    id="1",
                    label="Button",
                    controlType="Button",
                ),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("empty name or meaning" in w for w in result.warnings)

    def test_skip_image_validation(self, tmp_path):
        spec = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["missing_screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    imageFiles=["missing_comp.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Button",
                    controlType="Button",
                ),
            ]
        )
        result = validate_spec(spec, skip_image_validation=True)
        assert result.valid is True
        assert not result.errors

    def test_error_multiple_screens(self, tmp_path):
        spec = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen A",
                    description="desc desc desc",
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="0",  # Duplicate screen ID
                    label="Screen B",
                    description="desc desc desc",
                    childrenIds=["2"],
                ),
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("defined exactly once" in e for e in result.errors)

    def test_error_zero_screens(self, tmp_path):
        spec = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(
                    id="1",
                    label="Component A",
                    description="desc desc desc",
                    childrenIds=["2"],
                )
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("defined exactly once" in e for e in result.errors)

    def test_error_duplicate_node_ids(self, tmp_path):
        spec = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(id="0", label="Screen", description="desc", childrenIds=["1"]),
                NodeSpec(id="1", label="Button A", controlType="Button"),
                NodeSpec(id="1", label="Button B", controlType="Button"),  # Duplicate ID
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("Duplicate node ID" in e for e in result.errors)

    def test_error_non_existent_child_id(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["99"],  # Non-existent child
                )
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("references non-existent child ID" in e for e in result.errors)

    def test_error_multiple_parents(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1", "2"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=["2"],  # Child ID 2 has parent 1
                ),
                NodeSpec(
                    id="2",  # Child ID 2 also has parent 0
                    label="Button",
                    controlType="Button",
                ),
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("has multiple parents" in e for e in result.errors)

    def test_error_cycle_detected(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp1.png").touch()
        (Path(tmp_path) / "comp2.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    imageFiles=["comp1.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Comp 2",
                    description="desc desc desc",
                    imageFiles=["comp2.png"],
                    childrenIds=["1"],  # Cycle: 1 -> 2 -> 1
                ),
            ]
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any("Cyclic reference detected" in e for e in result.errors)


class TestUnitLimitValidation:
    """Tests for the unit limit complexity budget validation."""

    def _make_nodes(self, count: int) -> list[NodeSpec]:
        return [
            NodeSpec(id=f"child_{i}", label=f"Child {i}", controlType="Button")
            for i in range(1, count + 1)
        ]

    def _make_apis(self, count: int) -> list[Api]:
        return [
            Api(api=f"GET API {i}", url=f"/api/{i}")
            for i in range(count)
        ]

    def test_screen_at_exactly_15_units_is_valid(self, tmp_path):
        """15 children × 1 = 15 units, exactly at limit."""
        (Path(tmp_path) / "screen.png").touch()
        children = self._make_nodes(15)
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=[c.id for c in children],
                )
            ] + children
        )
        result = validate_spec(spec)
        assert not any("unit limit" in e for e in result.errors)

    def test_screen_exceeds_unit_limit(self, tmp_path):
        """13 children + 1 API = 13 + 3 = 16 units, over the limit."""
        (Path(tmp_path) / "screen.png").touch()
        children = self._make_nodes(13)
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=[c.id for c in children],
                    apis=self._make_apis(1),
                )
            ] + children
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any(
            "Screen 'Test' exceeds the unit limit: 16/15" in e for e in result.errors
        )

    def test_component_at_exactly_15_units_is_valid(self, tmp_path):
        """12 children + 1 API = 12 + 3 = 15 units, exactly at limit."""
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        children = self._make_nodes(12)
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Big Component",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=[c.id for c in children],
                    interactions=[Interaction(action="Click", reaction="React")],
                    apis=self._make_apis(1),
                ),
            ] + children,
        )
        result = validate_spec(spec)
        assert not any("unit limit" in e for e in result.errors)

    def test_component_exceeds_unit_limit(self, tmp_path):
        """4 children + 4 APIs = 4 + 12 = 16 units, over the limit."""
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        children = self._make_nodes(4)
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Heavy Component",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=[c.id for c in children],
                    interactions=[Interaction(action="Click", reaction="React")],
                    apis=self._make_apis(4),
                ),
            ] + children,
        )
        result = validate_spec(spec)
        assert result.valid is False
        assert any(
            "Component 'Heavy Component' (id=1) exceeds the unit limit: 16/15" in e
            for e in result.errors
        )

    def test_warnings_unreachable_orphan_nodes(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
                NodeSpec(id="2", label="Orphan Element", controlType="Text"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("never referenced in the tree hierarchy" in w for w in result.warnings)

    def test_warnings_component_with_control_type(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        (Path(tmp_path) / "comp.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Component with ControlType",
                    controlType="Button",
                    description="desc desc desc",
                    imageFiles=["comp.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(id="2", label="Child", controlType="Text"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("specifies a controlType" in w for w in result.warnings)

    def test_warnings_empty_interactions(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    childrenIds=["1"],
                    interactions=[Interaction(action=" ", reaction="Reaction")],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("Interaction at index 0 with empty action" in w for w in result.warnings)



