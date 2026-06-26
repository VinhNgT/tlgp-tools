"""Tests for validation logic."""

from doc_generator.models import (
    AnalysisComponent,
    AnalysisData,
    Api,
    ChildElement,
    Discrepancy,
    Interaction,
    Screen,
)
from doc_generator.validation import validate_analysis


def _minimal_analysis(tmp_path, **overrides) -> AnalysisData:
    defaults = {
        "sectionPrefix": "1.1",
        "imageDir": str(tmp_path),
        "screen": Screen(
            name="Test",
            description="desc",
            imageFiles=["screen.png"],
            topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
            apis=[Api(number=1, method="GET", title="Test", url="/test")],
        ),
        "components": [],
        "discrepancies": [],
    }
    defaults.update(overrides)
    return AnalysisData(**defaults)


class TestValidateAnalysis:
    def test_valid_analysis(self, tmp_path):
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
                    children=[
                        ChildElement(stt=1, label="Button", controlType="Button")
                    ],
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
                    children=[ChildElement(stt=1, label="B", controlType="B")]
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
                    children=[ChildElement(stt=1, label="B", controlType="B")]
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
                    children=[]
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("no children specified" in err for err in result.errors)

    def test_warnings_empty_control_type(self, tmp_path):
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
                    children=[ChildElement(stt=1, label="Label", controlType="")],
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty controlType" in w for w in result.warnings)

    def test_warnings_no_apis(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[],
            ),
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("No APIs defined" in w for w in result.warnings)

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
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
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
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[Api(number=1, method="GET", title="Test", url="/test")],
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
                    children=[ChildElement(stt=1, label="B", controlType="B")]
                )
            ],
        )

        result = validate_analysis(analysis)
        assert result.valid is False
        assert any("no imageFile specified" in err for err in result.errors)

    def test_statistics_include_screen_data(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(tmp_path)
        # Add 1 screen interaction and 1 screen child
        analysis.screen.interactions.append(Interaction(
            action="click",
            reaction="navigate"
        ))
        analysis.screen.topLevelChildren.append(ChildElement(stt=1, label="label", controlType="type"))

        result = validate_analysis(analysis)
        # The base _minimal_analysis might have some ui_elements or interactions,
        # but we know we added 1 to screen.
        assert result.ui_elements >= 1
        assert result.interactions >= 1
