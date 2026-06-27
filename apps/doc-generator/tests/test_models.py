"""Tests for Pydantic models."""

import pytest
from doc_generator.models import (
    AnalysisComponent,
    AnalysisData,
    Api,
    ApiParam,
    ComponentReferenceElement,
    Interaction,
    PrimitiveElement,
    Screen,
    ApiSchema,
)
from pydantic import ValidationError


class TestPrimitiveElement:
    def test_required_fields(self):
        c = PrimitiveElement(label="Submit", controlType="Button")
        assert c.type == "primitive"
        assert c.label == "Submit"
        assert c.controlType == "Button"
        assert c.required == ""
        assert c.maxLength == ""
        assert c.editable == ""
        assert c.description == ""


class TestComponentReferenceElement:
    def test_required_fields(self):
        c = ComponentReferenceElement(componentId=5)
        assert c.type == "component"
        assert c.componentId == 5
        assert c.label == ""
        assert c.description == ""
        assert c.controlType == "Component"


class TestInteraction:
    def test_required_fields(self):
        i = Interaction(action="Click", reaction="Submits form")
        assert i.action == "Click"
        assert i.reaction == "Submits form"


class TestApiParam:
    def test_required_fields(self):
        p = ApiParam(name="id")
        assert p.name == "id"
        assert p.meaning == ""
        assert p.dataType == ""
        assert p.required == ""


class TestApiSchema:
    def test_minimal(self):
        s = ApiSchema(name="UserDTO")
        assert s.name == "UserDTO"
        assert s.fieldRef == ""
        assert s.fields == []


class TestApi:
    def test_minimal(self):
        a = Api(method="GET", title="List", url="/api/list")
        assert a.method == "GET"
        assert a.title == "List"
        assert a.url == "/api/list"
        assert a.requestParams == []
        assert a.schemas == {}

    def test_with_sub_dtos(self):
        a = Api(
            method="GET",
            title="Detail",
            url="/api/detail",
            schemas={
                "PriceTiersDTO": ApiSchema(
                    name="PriceTiersDTO",
                    fieldRef="price_tiers",
                    fields=[
                        ApiParam(name="min_qty", dataType="int"),
                    ],
                )
            },
        )
        assert len(a.schemas) == 1
        assert "PriceTiersDTO" in a.schemas


class TestAnalysisComponent:
    def test_leaf_cannot_have_children(self):
        with pytest.raises(ValidationError, match="cannot have children"):
            AnalysisComponent(
                id=1,
                label="Leaf",
                isLeaf=True,
                children=[PrimitiveElement(label="Btn", controlType="Button")],
            )

    def test_leaf_cannot_have_apis(self):
        with pytest.raises(ValidationError, match="cannot have API documentation"):
            AnalysisComponent(
                id=1,
                label="Leaf",
                isLeaf=True,
                apis=[Api(method="GET", title="Test", url="/test")],
            )

    def test_with_children_and_interactions(self):
        c = AnalysisComponent(
            id=1,
            label="Form",
            isLeaf=False,
            children=[PrimitiveElement(label="Submit", controlType="Button")],
            interactions=[Interaction(action="Tap", reaction="Submit")],
        )
        assert len(c.children) == 1
        assert len(c.interactions) == 1


class TestScreen:
    def test_defaults(self):
        s = Screen(name="Home")
        assert s.imageFiles == []
        assert s.topLevelChildren == []
        assert s.interactions == []


class TestAnalysisData:
    def test_valid_with_real_dir(self, tmp_path):
        data = AnalysisData(
            sectionPrefix="1.1",
            imageDir=str(tmp_path),
            screen=Screen(name="Test"),
        )
        assert data.sectionPrefix == "1.1"
        assert data.components == {}
        assert data.all_apis == []
        assert data.discrepancies == []

    def test_resolve_image(self, tmp_path):
        (tmp_path / "test.png").touch()
        data = AnalysisData(
            imageDir=str(tmp_path),
            screen=Screen(name="Test"),
        )
        resolved = data.resolve_image("test.png")
        assert resolved == tmp_path / "test.png"
        assert resolved.exists()


class TestJsonRoundTrip:
    def test_serialize_and_deserialize(self, tmp_path):
        data = AnalysisData(
            sectionPrefix="2.3",
            imageDir=str(tmp_path),
            screen=Screen(
                name="Cart",
                apis=[
                    Api(method="POST", title="Add to cart", url="/api/cart"),
                ],
            ),
            components={
                1: AnalysisComponent(
                    id=1,
                    label="Header",
                    children=[
                        PrimitiveElement(label="Back", controlType="Icon"),
                    ],
                )
            },
        )
        json_str = data.model_dump_json()
        restored = AnalysisData.model_validate_json(json_str)
        assert restored.sectionPrefix == "2.3"
        assert restored.screen.name == "Cart"
        assert len(restored.components) == 1
        assert 1 in restored.components
        assert restored.components[1].label == "Header"
