"""Tests for validation logic."""

import pytest
from doc_generator.models import (
    AnalysisComponent,
    AnalysisData,
    Api,
    ApiParam,
    ChildElement,
    Discrepancy,
    Interaction,
    Screen,
    SubDto,
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
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Comp 1", controlType="Component")],
                apis=[Api(number=1, method="GET", title="Test", url="/test")],
            ),
            components=[
                AnalysisComponent(
                    id=1,
                    label="Comp 1",
                    description="desc desc desc",
                    imageFile="comp.png",
                    children=[
                        ChildElement(stt=1, label="Button", controlType="Button")
                    ],
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

    def test_warnings_non_contiguous_api_numbering(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(number=1, method="GET", title="Test 1", url="/test1"),
                    Api(number=3, method="GET", title="Test 3", url="/test3"),
                ],
            ),
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("missing number(s) 2" in w for w in result.warnings)

    def test_warnings_undocumented_request_body(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1,
                        method="POST",
                        title="Test",
                        url="/test",
                        requestBodyType="TestRequestDto",
                        requestParams=[],
                        subDtos=[],
                    )
                ],
            ),
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("declares requestBodyType 'TestRequestDto' but has no request parameters" in w for w in result.warnings)

    def test_no_warning_when_request_body_documented_in_subdtos(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1,
                        method="POST",
                        title="Test",
                        url="/test",
                        requestBodyType="TestRequestDto",
                        requestParams=[],
                        subDtos=[
                            SubDto(
                                name="TestRequestDto",
                                fieldRef="",
                                fields=[ApiParam(name="id", meaning="id", required="Có", dataType="int", limit="", defaultValue="")]
                            )
                        ],
                    )
                ],
            ),
        )

        result = validate_analysis(analysis)
        assert result.valid is True
        assert not any("declares requestBodyType" in w for w in result.warnings)

    def test_warnings_duplicate_stt(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[
                    ChildElement(stt=1, label="A", controlType="Button"),
                    ChildElement(stt=1, label="B", controlType="Text"),
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("Duplicate stt 1 in Screen 'Test'" in w for w in result.warnings)

    def test_warnings_undocumented_response_type(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1,
                        method="GET",
                        title="Test",
                        url="/test",
                        responseType="TestResponseDto",
                        responseFields=[],
                        subDtos=[],
                    )
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("declares responseType 'TestResponseDto' but has no response fields" in w for w in result.warnings)

    def test_warnings_dangling_subdto(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1,
                        method="GET",
                        title="Test",
                        url="/test",
                        subDtos=[
                            SubDto(name="UnusedDto", fields=[])
                        ],
                    )
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("declares SubDto 'UnusedDto', but it is never referenced" in w for w in result.warnings)

    def test_error_leaf_cannot_have_children(self):
        with pytest.raises(ValidationError, match="is a leaf component and cannot have children"):
            AnalysisComponent(
                id=1,
                label="Leaf",
                isLeaf=True,
                children=[ChildElement(stt=1, label="A", controlType="Button")]
            )

    def test_error_duplicate_component_id(self, tmp_path):
        (tmp_path / "screen.png").touch()
        with pytest.raises(ValidationError, match="Component ID 1 is duplicated across components"):
            _minimal_analysis(
                tmp_path,
                components=[
                    AnalysisComponent(id=1, label="Comp 1", imageFile="screen.png", children=[ChildElement(stt=1, label="A", controlType="B")]),
                    AnalysisComponent(id=1, label="Comp 2", imageFile="screen.png", children=[ChildElement(stt=1, label="A", controlType="B")])
                ]
            )

    def test_error_api_number_less_than_one(self):
        with pytest.raises(ValidationError, match="API number must be >= 1"):
            Api(number=0, method="GET", title="Test", url="/")

    def test_error_api_method_invalid(self):
        with pytest.raises(ValidationError, match="API method must be one of"):
            Api(number=1, method="GETT", title="Test", url="/")

    def test_api_method_normalized(self):
        api = Api(number=1, method=" get ", title="Test", url="/")
        assert api.method == "GET"

    def test_error_image_path_traversal(self, tmp_path):
        (tmp_path / "screen.png").touch()
        outside_file = tmp_path.parent / "outside.png"
        outside_file.touch()

        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1, label="Comp 1", imageFile="../outside.png", children=[ChildElement(stt=1, label="A", controlType="B")]
                )
            ]
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
                    id=1, label=" ", description="desc desc desc", imageFile="screen.png", children=[ChildElement(stt=1, label=" ", controlType="B")],
                    interactions=[Interaction(action="A", reaction="B")]
                )
            ]
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty label" in w for w in result.warnings)

    def test_warnings_empty_interactions(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1, label="Comp", description="desc desc desc", imageFile="screen.png", children=[ChildElement(stt=1, label="A", controlType="B")],
                    interactions=[]
                )
            ]
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("zero interactions" in w for w in result.warnings)

    def test_warnings_empty_action_reaction(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1, label="Comp", description="desc desc desc", imageFile="screen.png", children=[ChildElement(stt=1, label="A", controlType="B")],
                    interactions=[Interaction(action=" ", reaction="A")]
                )
            ]
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty action/reaction" in w for w in result.warnings)

    def test_warnings_stt_starts_at_2(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[
                    ChildElement(stt=2, label="A", controlType="Button"),
                    ChildElement(stt=3, label="B", controlType="Text"),
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("starts at 2, expected 1" in w for w in result.warnings)

    def test_warnings_api_numbering_starts_at_2(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(number=2, method="GET", title="Test", url="/test")
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("starts at 2, expected 1" in w for w in result.warnings)

    def test_error_api_url_no_slash(self):
        with pytest.raises(ValidationError, match="API url must start with"):
            Api(number=1, method="GET", title="Test", url="test")

    def test_warnings_orphan_component(self, tmp_path):
        (tmp_path / "screen.png").touch()
        (tmp_path / "comp.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                AnalysisComponent(
                    id=1, label="Orphan", description="desc desc desc", imageFile="comp.png", children=[ChildElement(stt=1, label="A", controlType="B")],
                    interactions=[Interaction(action="A", reaction="B")]
                )
            ]
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
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("suspiciously short" in w for w in result.warnings)

    def test_error_duplicate_api_number(self, tmp_path):
        (tmp_path / "screen.png").touch()
        with pytest.raises(ValidationError, match="defined in multiple places"):
            _minimal_analysis(
                tmp_path,
                screen=Screen(
                    name="Test",
                    description="desc desc desc",
                    imageFiles=["screen.png"],
                    topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                    apis=[
                        Api(number=1, method="GET", title="Test 1", url="/test1"),
                        Api(number=1, method="POST", title="Test 2", url="/test2")
                    ],
                ),
            )

    def test_warnings_missing_subdto(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1, method="GET", title="Test", url="/test",
                        requestBodyType="MissingDto",
                        subDtos=[]
                    )
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("not defined in subDtos" in w for w in result.warnings)

    def test_warnings_empty_api_param(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Test", controlType="Button")],
                apis=[
                    Api(
                        number=1, method="GET", title="Test", url="/test",
                        requestParams=[ApiParam(name=" ", meaning="valid", dataType="String")]
                    )
                ],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("empty name or meaning" in w for w in result.warnings)

    def test_warnings_component_cross_check(self, tmp_path):
        (tmp_path / "screen.png").touch()
        analysis = _minimal_analysis(
            tmp_path,
            screen=Screen(
                name="Test",
                description="desc desc desc",
                imageFiles=["screen.png"],
                topLevelChildren=[ChildElement(stt=1, label="Missing Comp", controlType="Component")],
            ),
        )
        result = validate_analysis(analysis)
        assert result.valid is True
        assert any("references non-existent component" in w for w in result.warnings)
