"""Tests for validation logic."""

import pytest
from doc_generator.models import (
    AnalysisComponent,
    AnalysisData,
    Api,
    ApiParam,
    ChildElement,
    ComponentReferenceElement,
    Discrepancy,
    Interaction,
    PrimitiveElement,
    Screen,
)
from doc_generator.validation import validate_analysis
from pydantic import ValidationError


def _minimal_analysis(tmp_path, **overrides) -> AnalysisData:
    defaults = {
        "sectionPrefix": "1.1",
        "imageDir": str(tmp_path),
        "screen": Screen(
            name="Test",
            description="desc desc desc",
            imageFiles=["screen.png"],
            topLevelChildren=[PrimitiveElement(label="Test", controlType="Button")],
            apis=[Api(method="GET", title="Test", url="/test")],
        ),
        "components": {},
        "discrepancies": [],
    }

    if "components" in overrides and isinstance(overrides["components"], list):
        overrides["components"] = {c.id: c for c in overrides["components"]}
    if "subDtos" in overrides and isinstance(overrides["subDtos"], list):
        overrides["subDtos"] = {d.name: d for d in overrides["subDtos"]}
    defaults.update(overrides)

    return AnalysisData(**defaults)


class TestValidateAnalysis:
    def test_valid_analysis(self, tmp_path):
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()

        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[
                    ComponentReferenceElement(label="Comp 1", componentId=99)
                ],
                apis=[Api(method="GET", title="Test", url="/test")],
            ),
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="desc desc desc",
                    imageFile="comp.png",
                    children=[PrimitiveElement(label="Button", controlType="Button")],
                    interactions=[Interaction(action="Click", reaction="Test")],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert not result.errors
        assert not result.warnings
        assert result.components == 1
        assert result.non_leaf == 1
        assert result.images == 2
        assert result.apis == 1

    def test_missing_images(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="desc",
                    imageFile="missing_comp.png",
                    children=[PrimitiveElement(label="B", controlType="B")],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert len(result.errors) == 2
        assert any("Screen image not found:" in err for err in result.errors)
        assert any("image not found:" in err for err in result.errors)

    def test_error_empty_description(self, tmp_path):
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="",
                    imageFile="comp.png",
                    children=[PrimitiveElement(label="B", controlType="B")],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("empty description" in err for err in result.errors)

    def test_error_empty_children(self, tmp_path):
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="desc",
                    imageFile="comp.png",
                    children=[],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("no children specified" in err for err in result.errors)

    def test_warnings_discrepancies(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            discrepancies=[
                Discrepancy(
                    location="Header",
                    imageObservation="Blue button",
                    codeObservation="Red button",
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("Discrepancy at 'Header'" in w for w in result.warnings)

    def test_error_empty_screen_description(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="",
                imageFiles=["screen.png"],
                topLevelChildren=[PrimitiveElement(label="Test", controlType="Button")],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("Screen description is empty" in err for err in result.errors)

    def test_error_empty_screen_children(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("Screen has no top-level children" in err for err in result.errors)

    def test_error_no_screen_images(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=[],
                topLevelChildren=[PrimitiveElement(label="Test", controlType="Button")],
                apis=[Api(method="GET", title="Test", url="/test")],
            ),
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("No screen-level images specified" in err for err in result.errors)

    def test_error_no_imageFile_in_component(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="desc",
                    imageFile=None,
                    children=[PrimitiveElement(label="B", controlType="B")],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("no imageFile specified" in err for err in result.errors)

    def test_error_leaf_cannot_have_children(self):
        with pytest.raises(
            ValidationError, match="is a leaf component and cannot have children"
        ):
            AnalysisComponent(
                id=1,
                label="Leaf",
                isLeaf=True,
                children=[PrimitiveElement(label="A", controlType="Button")],
            )

    def test_error_image_path_traversal(self, tmp_path):
        (tmp_path / "screen.png").touch()
        outside_file = tmp_path.parent / "outside.png"
        outside_file.touch()

        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    imageFile="../outside.png",
                    children=[PrimitiveElement(label="A", controlType="B")],
                )
            ],
        )
        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("escapes imageDir" in e for e in result.errors)
        outside_file.unlink()

    def test_warnings_empty_labels(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label=" ",
                    description="desc desc desc",
                    imageFile="screen.png",
                    children=[PrimitiveElement(label=" ", controlType="B")],
                    interactions=[Interaction(action="A", reaction="B")],
                )
            ],
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty label" in w for w in result.warnings)

    def test_warnings_orphan_component(self, tmp_path):
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Orphan",
                    description="desc desc desc",
                    imageFile="comp.png",
                    children=[PrimitiveElement(label="A", controlType="B")],
                    interactions=[Interaction(action="A", reaction="B")],
                )
            ],
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("never referenced as a child" in w for w in result.warnings)

    def test_warnings_short_description(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="short",
                imageFiles=["screen.png"],
                topLevelChildren=[PrimitiveElement(label="Test", controlType="Button")],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("suspiciously short" in w for w in result.warnings)

    def test_warnings_empty_api_param(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[PrimitiveElement(label="Test", controlType="Button")],
                apis=[
                    Api(
                        method="GET",
                        title="Test",
                        url="/test",
                        requestParams=[
                            ApiParam(name=" ", meaning="valid", dataType="String")
                        ],
                    )
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty name or meaning" in w for w in result.warnings)


class TestUnitLimitValidation:
    """Tests for the unit limit complexity budget validation."""

    def _make_children(self, count: int) -> list[ChildElement]:
        return [
            PrimitiveElement(stt=i, label=f"Child {i}", controlType="Button")
            for i in range(1, count + 1)
        ]

    def _make_apis(self, count: int, start_number: int = 1) -> list[Api]:
        return [
            Api(
                number=start_number + i, method="GET", title=f"API {i}", url=f"/api/{i}"
            )
            for i in range(count)
        ]

    def test_screen_at_exactly_15_units_is_valid(self, tmp_path):
        """15 children × 1 = 15 units, exactly at limit."""
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=self._make_children(15),
            ),
        )
        result = validate_analysis(analysis)
        assert not any("unit limit" in e for e in result.errors)

    def test_screen_exceeds_unit_limit(self, tmp_path):
        """13 children + 1 API = 13 + 3 = 16 units, over the limit."""
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=self._make_children(13),
                apis=self._make_apis(1),
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is False
        assert any(
            "Screen 'Test' exceeds the unit limit: 16/15" in e for e in result.errors
        )

    def test_component_at_exactly_15_units_is_valid(self, tmp_path):
        """12 children + 1 API = 12 + 3 = 15 units, exactly at limit."""
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Big Component",
                    description="desc desc desc",
                    imageFile="comp.png",
                    children=self._make_children(12),
                    interactions=[Interaction(action="Click", reaction="React")],
                    apis=self._make_apis(1, start_number=2),
                ),
            ],
        )
        result = validate_analysis(analysis)
        assert not any("unit limit" in e for e in result.errors)

    def test_component_exceeds_unit_limit(self, tmp_path):
        """4 children + 4 APIs = 4 + 12 = 16 units, over the limit."""
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1,
                    label="Heavy Component",
                    description="desc desc desc",
                    imageFile="comp.png",
                    children=self._make_children(4),
                    interactions=[Interaction(action="Click", reaction="React")],
                    apis=self._make_apis(4, start_number=2),
                ),
            ],
        )
        result = validate_analysis(analysis)
        assert result.valid is False
        assert any(
            "Component 'Heavy Component' (id=1) exceeds the unit limit: 16/15" in e
            for e in result.errors
        )

    def test_only_offending_component_flagged(self, tmp_path):
        """When multiple components exist, only the one over the limit is flagged."""
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp_a.png").touch()
        (tmp_path / "comp_b.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[
                    ComponentReferenceElement(label="OK Component", componentId=99),
                    ComponentReferenceElement(label="Over Component", componentId=99),
                ],
            ),
            components=[
                AnalysisComponent(
                    id=1,
                    label="OK Component",
                    description="desc desc desc",
                    imageFile="comp_a.png",
                    children=self._make_children(2),
                    interactions=[Interaction(action="A", reaction="B")],
                ),
                AnalysisComponent(
                    id=2,
                    label="Over Component",
                    description="desc desc desc",
                    imageFile="comp_b.png",
                    children=self._make_children(4),
                    interactions=[Interaction(action="A", reaction="B")],
                    apis=self._make_apis(4, start_number=2),
                ),
            ],
        )
        result = validate_analysis(analysis)
        unit_limit_errors = [e for e in result.errors if "unit limit" in e]
        assert len(unit_limit_errors) == 1
        assert "Over Component" in unit_limit_errors[0]
        assert "OK Component" not in unit_limit_errors[0]

    def test_leaf_components_never_flagged(self, tmp_path):
        """Leaf components have no children or APIs — unit check is skipped."""
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(id=1, label="Leaf", isLeaf=True),
            ],
        )
        result = validate_analysis(analysis)
        assert not any("unit limit" in e for e in result.errors)

    def test_error_message_contains_breakdown(self, tmp_path):
        """Error message includes annotation count, API count, and total."""
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=self._make_children(10),
                apis=self._make_apis(2),
            ),
        )
        # 10 children + 2 APIs = 10 + 6 = 16 units
        result = validate_analysis(analysis)
        assert result.valid is False
        err = [e for e in result.errors if "unit limit" in e][0]
        assert "16/15" in err
        assert "10 annotations" in err
        assert "2 APIs" in err
