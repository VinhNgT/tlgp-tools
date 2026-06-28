"""Tests for Pydantic models."""

import pytest
from doc_generator.models import (
    NodeSpec,
    ScreenSpec,
    Api,
    ApiParam,
    Interaction,
    ApiPayload,
)
from pydantic import ValidationError


class TestNodeSpec:
    def test_required_fields(self):
        c = NodeSpec(id=1, label="Submit", controlType="Button")
        assert c.id == 1
        assert c.label == "Submit"
        assert c.controlType == "Button"
        assert c.required is None
        assert c.maxLength is None
        assert c.editable is None
        assert c.description is None
        assert c.childrenIds == []
        assert c.interactions == []
        assert c.apis == []


class TestInteraction:
    def test_required_fields(self):
        i = Interaction(action="Click", reaction="Submits form")
        assert i.action == "Click"
        assert i.reaction == "Submits form"


class TestApiParam:
    def test_required_fields(self):
        p = ApiParam(name="id")
        assert p.name == "id"
        assert p.description is None
        assert p.type is None
        assert p.required is None


class TestApiPayload:
    def test_minimal(self):
        s = ApiPayload(type="UserDTO")
        assert s.type == "UserDTO"
        assert s.fields == []


class TestApi:
    def test_minimal(self):
        a = Api(name="GET List", url="/api/list")
        assert a.name == "GET List"
        assert a.url == "/api/list"
        assert a.request == []
        assert a.response == []

    def test_with_sub_dtos(self):
        a = Api(
            name="GET Detail",
            url="/api/detail",
            requestRootType="PriceTiersDTO",
            request=[
                ApiPayload(
                    type="PriceTiersDTO",
                    fields=[
                        ApiParam(name="min_qty", type="int"),
                    ],
                )
            ],
        )
        assert len(a.request) == 1
        assert a.request[0].type == "PriceTiersDTO"


class TestScreenSpec:
    def test_valid_with_real_dir(self, tmp_path):
        data = ScreenSpec(
            sectionPrefix="1.1",
            nodes=[NodeSpec(id=0, label="Test")],
        )
        assert data.sectionPrefix == "1.1"
        assert len(data.nodes) == 1
        assert data.all_apis == []

    def test_resolve_image(self, tmp_path):
        (tmp_path / "test.png").touch()
        data = ScreenSpec(
            nodes=[NodeSpec(id=0, label="Test")],
        )
        resolved = data.resolve_annotated_image(str(tmp_path / "test.png"))
        assert resolved == tmp_path / "test.png"
        assert resolved.exists()


class TestJsonRoundTrip:
    def test_serialize_and_deserialize(self, tmp_path):
        data = ScreenSpec(
            sectionPrefix="2.3",
            nodes=[
                NodeSpec(
                    id=1,
                    label="Header",
                    childrenIds=[2],
                ),
                NodeSpec(
                    id=2,
                    label="Back",
                    controlType="Icon",
                ),
                NodeSpec(
                    id=0,
                    label="Cart",
                    childrenIds=[1],
                    apis=[
                        Api(name="POST Add to cart", url="/api/cart"),
                    ],
                ),
            ],
        )
        json_str = data.model_dump_json()
        restored = ScreenSpec.model_validate_json(json_str)
        assert restored.sectionPrefix == "2.3"
        assert restored.screen.label == "Cart"
        assert len(restored.nodes) == 3
        # Assert specific node details
        nodes_dict = restored.nodes_map
        assert nodes_dict[1].label == "Header"
        assert nodes_dict[2].controlType == "Icon"


class TestSampleSpecFixture:
    def test_sample_spec_parses(self):
        import json
        from pathlib import Path
        fixture_path = Path(__file__).parent / "fixtures" / "sample_spec.json"
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        data = ScreenSpec.model_validate(raw)
        assert len(data.all_apis) == 3
        # Assert type and layout on Cart Add
        cart_add_api = [a for a in data.all_apis if "Thêm sản phẩm" in a.name][0]
        assert len(cart_add_api.request) == 2
        assert cart_add_api.request[0].type == "AddToCartRequestDto"
        assert cart_add_api.request[1].type == "ProductOptionDto"
