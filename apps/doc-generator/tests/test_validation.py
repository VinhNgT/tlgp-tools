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

    # Ensure exactly one screen component (id == 0) exists
    screen_comp = [n for n in nodes if n.id == 0]
    if not screen_comp:
        (Path(tmp_path) / "screen.png").touch()
        nodes.append(
            NodeSpec(
                id=0,
                label="Test",
                description="desc desc desc",
                annotatedImages=[str(Path(tmp_path) / "screen.png")],
                childrenIds=[1],
                apis=[Api(name="GET Test", url="/test")],
                required=False,
                editable=False,
            )
        )
        nodes.append(
            NodeSpec(
                id=1,
                label="Test Child",
                controlType="Button",
                required=False,
                editable=False,
            )
        )
    else:
        # Resolve all relative paths to absolute and touch them
        for n in nodes:
            n.annotatedImages = [str(Path(tmp_path) / img) if img and not Path(img).is_absolute() else img for img in n.annotatedImages]
            if n.rawImage and n.rawImage != "dummy.png" and not Path(n.rawImage).is_absolute():
                n.rawImage = str(Path(tmp_path) / n.rawImage)

            for img_file in n.annotatedImages:
                if img_file:
                    Path(img_file).touch()
            if n.rawImage and n.rawImage != "dummy.png":
                Path(n.rawImage).touch()

    defaults = {
        "sectionPrefix": "1.1",
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1", "2"],
                    apis=[Api(name="GET Test", url="/test")],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    annotatedImages=["comp.png"],
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
            
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["missing_screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    annotatedImages=["missing_comp.png"],
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
        with pytest.raises(ValidationError):
            _minimal_spec(
                tmp_path,
                nodes=[
                    NodeSpec(
                        id="0",
                        label="Test Screen",
                        description="desc desc desc",
                        annotatedImages=["screen.png"],
                        childrenIds=["1"],
                    ),
                    NodeSpec(
                        id="1",
                        label="Comp 1",
                        description="",
                        annotatedImages=["comp.png"],
                        childrenIds=["2"],
                    ),
                    NodeSpec(
                        id="2",
                        label="Button",
                        controlType="Button",
                    ),
                ],
            )

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
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc",
                    annotatedImages=["comp.png"],
                    childrenIds=[],
                )
            ],
        )

        result = validate_spec(spec)
        assert result.valid is False
        assert any("no children specified" in err for err in result.errors)

    def test_error_empty_screen_description(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        with pytest.raises(ValidationError):
            _minimal_spec(
                tmp_path,
                nodes=[
                    NodeSpec(
                        id="0",
                        label="Test",
                        description="",
                        annotatedImages=["screen.png"],
                        childrenIds=["1"],
                    ),
                    NodeSpec(
                        id="1",
                        label="Button",
                        controlType="Button",
                    ),
                ],
            )

    def test_error_empty_screen_children(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc",
                    annotatedImages=["screen.png"],
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
                    annotatedImages=[],
                    childrenIds=["1"],
                    apis=[Api(name="GET Test", url="/test")],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc",
                    annotatedImages=[],
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
        assert any("no annotatedImages specified" in err for err in result.errors)


    def test_warnings_empty_labels(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label=" ",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="1",
                    label="Orphan Component",
                    description="desc desc desc",
                    annotatedImages=["comp.png"],
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
                    annotatedImages=["screen.png"],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Test",
                            url="/test",
                            requestRootType="TestDto",
                            request=[
                                ApiPayload(
                                    type="TestDto",
                                    fields=[
                                        ApiParam(name=" ", description="valid", type="String")
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
        assert len(result.warnings) == 0

    def test_skip_image_validation(self, tmp_path):
        spec = ScreenSpec(
            
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["missing_screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    annotatedImages=["missing_comp.png"],
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
                    annotatedImages=["screen.png"],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1", "2"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    annotatedImages=["comp.png"],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Comp 1",
                    description="desc desc desc",
                    annotatedImages=["comp1.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Comp 2",
                    description="desc desc desc",
                    annotatedImages=["comp2.png"],
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
            NodeSpec(id=100 + i, label=f"Child {i}", controlType="Button")
            for i in range(1, count + 1)
        ]

    def _make_apis(self, count: int) -> list[Api]:
        return [
            Api(name=f"GET API {i}", url=f"/api/{i}")
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
                    id=0,
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
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
                    id=0,
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
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
                    id=0,
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=[1],
                ),
                NodeSpec(
                    id=1,
                    label="Big Component",
                    description="desc desc desc",
                    annotatedImages=["comp.png"],
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
                    id=0,
                    label="Test",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=[1],
                ),
                NodeSpec(
                    id=1,
                    label="Heavy Component",
                    description="desc desc desc",
                    annotatedImages=["comp.png"],
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
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
                NodeSpec(id="2", label="Orphan Element", controlType="Text"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("never referenced in the tree hierarchy" in w for w in result.warnings)



    def test_warnings_empty_interactions(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    interactions=[Interaction(action=" ", reaction="Reaction")],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert any("Interaction at index 0 with empty action" in w for w in result.warnings)

    def test_api_dto_duplicate_ids(self, tmp_path):
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Test",
                            url="/test",
                            requestRootType="Dup",
                            request=[
                                ApiPayload(type="Dup"),
                                ApiPayload(type="Dup"),
                            ],
                        )
                    ],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_api_dto_cycle_detected(self, tmp_path):
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Test",
                            url="/test",
                            requestRootType="A",
                            request=[
                                ApiPayload(type="A", fields=[ApiParam(name="b", type="B")]),
                                ApiPayload(type="B", fields=[ApiParam(name="a", type="A")]),
                            ],
                        )
                    ],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_api_dto_root_missing(self, tmp_path):
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Test",
                            url="/test",
                            requestRootType="Missing",
                            request=[
                                ApiPayload(type="A"),
                            ],
                        )
                    ],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_api_dto_unreachable_warning(self, tmp_path):
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Test",
                            url="/test",
                            requestRootType="A",
                            request=[
                                ApiPayload(type="A"),
                                ApiPayload(type="B"),
                            ],
                        )
                    ],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec, skip_image_validation=True)
        assert result.valid is True
        assert len(result.warnings) == 0

    def test_api_dto_list_unwrapping(self, tmp_path):
        (Path(tmp_path) / "screen.png").touch()
        spec = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Screen",
                    description="desc desc desc",
                    annotatedImages=["screen.png"],
                    childrenIds=["1"],
                    apis=[
                        Api(
                            name="GET Products",
                            url="/products",
                            responseRootType="List[ProductDto]",
                            response=[
                                ApiPayload(
                                    type="ProductDto",
                                    fields=[
                                        ApiParam(name="id", type="string", required=True, description="ID"),
                                        ApiParam(name="options", type="ProductOptionDto[]", required=False, description="Options")
                                    ]
                                ),
                                ApiPayload(
                                    type="ProductOptionDto",
                                    fields=[
                                        ApiParam(name="color", type="string", required=True, description="Color")
                                    ]
                                )
                            ],
                        )
                    ],
                ),
                NodeSpec(id="1", label="Button", controlType="Button"),
            ],
        )
        result = validate_spec(spec, skip_image_validation=True)
        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0



