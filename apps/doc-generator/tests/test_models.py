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
        c = NodeSpec(id="1", label="Submit", controlType="Button")
        assert c.id == "1"
        assert c.label == "Submit"
        assert c.controlType == "Button"
        assert c.required == ""
        assert c.maxLength == ""
        assert c.editable == ""
        assert c.description == ""
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
        assert p.meaning == ""
        assert p.dataType == ""
        assert p.required == ""


class TestApiPayload:
    def test_minimal(self):
        s = ApiPayload(type="UserDTO")
        assert s.type == "UserDTO"
        assert s.parentType is None
        assert s.fields == []


class TestApi:
    def test_minimal(self):
        a = Api(api="GET List", url="/api/list")
        assert a.api == "GET List"
        assert a.url == "/api/list"
        assert a.request == []
        assert a.response == []

    def test_with_sub_dtos(self):
        a = Api(
            api="GET Detail",
            url="/api/detail",
            request=[
                ApiPayload(
                    type="PriceTiersDTO",
                    parentType="RootDto",
                    fields=[
                        ApiParam(name="min_qty", dataType="int"),
                    ],
                )
            ],
        )
        assert len(a.request) == 1
        assert a.request[0].type == "PriceTiersDTO"
        assert a.request[0].parentType == "RootDto"


class TestScreenSpec:
    def test_valid_with_real_dir(self, tmp_path):
        data = ScreenSpec(
            sectionPrefix="1.1",
            imageDir=str(tmp_path),
            nodes=[NodeSpec(id="0", label="Test")],
        )
        assert data.sectionPrefix == "1.1"
        assert len(data.nodes) == 1
        assert data.all_apis == []

    def test_resolve_image(self, tmp_path):
        (tmp_path / "test.png").touch()
        data = ScreenSpec(
            imageDir=str(tmp_path),
            nodes=[NodeSpec(id="0", label="Test")],
        )
        resolved = data.resolve_image("test.png")
        assert resolved == tmp_path / "test.png"
        assert resolved.exists()


class TestJsonRoundTrip:
    def test_serialize_and_deserialize(self, tmp_path):
        data = ScreenSpec(
            sectionPrefix="2.3",
            imageDir=str(tmp_path),
            nodes=[
                NodeSpec(
                    id="1",
                    label="Header",
                    childrenIds=["2"],
                ),
                NodeSpec(
                    id="2",
                    label="Back",
                    controlType="Icon",
                ),
                NodeSpec(
                    id="0",
                    label="Cart",
                    childrenIds=["1"],
                    apis=[
                        Api(api="POST Add to cart", url="/api/cart"),
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
        assert nodes_dict["1"].label == "Header"
        assert nodes_dict["2"].controlType == "Icon"


class TestSampleSpecFixture:
    def test_sample_spec_parses(self):
        import json
        from pathlib import Path
        fixture_path = Path(__file__).parent / "fixtures" / "sample_spec.json"
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        data = ScreenSpec.model_validate(raw)
        assert len(data.all_apis) == 3
        # Assert type/parentType on Cart Add
        cart_add_api = [a for a in data.all_apis if "Thêm sản phẩm" in a.api][0]
        assert len(cart_add_api.request) == 2
        assert cart_add_api.request[0].type == "AddToCartRequestDto"
        assert cart_add_api.request[0].parentType is None
        assert cart_add_api.request[1].type == "ProductOptionDto"
        assert cart_add_api.request[1].parentType == "AddToCartRequestDto"
