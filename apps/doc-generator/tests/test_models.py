"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError
from tlgp_contracts import (
    Api,
    ApiParam,
    ApiPayload,
    Interaction,
    NodeSpec,
    ScreenSpec,
)
from tlgp_contracts.spec import Bounds


class TestNodeSpec:
    def test_required_fields(self):
        c = NodeSpec(
            id=1,
            label="Submit",
            controlType="Button",
            absoluteBounds=Bounds(x=0, y=0, w=100, h=50),
            required=True,
            editable=True,
            description="Submit button component",
            rawImage="raw/submit.png"
        )
        assert c.id == "1"
        assert c.label == "Submit"
        assert c.controlType == "Button"
        assert c.required is True
        assert c.maxLength is None
        assert c.editable is True
        assert c.description == "Submit button component"
        assert c.rawImage == "raw/submit.png"
        assert c.childrenIds == []
        assert c.interactions == []
        assert c.apis == []


class TestNodeSpecMaxLength:
    def test_valid_integer_maxLength(self):
        c = NodeSpec(
            id=1,
            label="Submit",
            controlType="Button",
            absoluteBounds=Bounds(x=0, y=0, w=100, h=50),
            required=True,
            editable=True,
            description="Submit button component",
            rawImage="raw/submit.png",
            maxLength=20
        )
        assert c.maxLength == 20

    def test_coerced_string_integer_maxLength(self):
        c = NodeSpec(
            id=1,
            label="Submit",
            controlType="Button",
            absoluteBounds=Bounds(x=0, y=0, w=100, h=50),
            required=True,
            editable=True,
            description="Submit button component",
            rawImage="raw/submit.png",
            maxLength="20"
        )
        assert c.maxLength == 20

    def test_invalid_string_maxLength(self):
        with pytest.raises(ValidationError):
            NodeSpec(
                id=1,
                label="Submit",
                controlType="Button",
                absoluteBounds=Bounds(x=0, y=0, w=100, h=50),
                required=True,
                editable=True,
                description="Submit button component",
                rawImage="raw/submit.png",
                maxLength="unlimited"
            )
class TestInteraction:
    def test_required_fields(self):
        i = Interaction(action="Click", reaction="Submits form")
        assert i.action == "Click"
        assert i.reaction == "Submits form"


class TestApiParam:
    def test_required_fields(self):
        p = ApiParam(name="id", description="ID field", required=True, type="int")
        assert p.name == "id"
        assert p.description == "ID field"
        assert p.type == "int"
        assert p.required is True


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
            nodes=[NodeSpec(id="root", label="Test")],
        )
        assert data.sectionPrefix == "1.1"
        assert len(data.nodes) == 1
        assert data.all_apis == []

    def test_resolve_image(self, tmp_path):
        (tmp_path / "test.png").touch()
        data = ScreenSpec(
            nodes=[NodeSpec(id="root", label="Test")],
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
                    id="root",
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
        # Assert type and layout on Cart Add
        cart_add_api = [a for a in data.all_apis if "Thêm sản phẩm" in a.name][0]
        assert len(cart_add_api.request) == 2
        assert cart_add_api.request[0].type == "AddToCartRequestDto"
        assert cart_add_api.request[1].type == "ProductOptionDto"

    def test_relative_path_resolver(self):
        from pathlib import Path
        spec = ScreenSpec(
            sectionPrefix="1.1",
            rootId=0,
            nodes=[
                NodeSpec(
                    id=0,
                    label="Test",
                    controlType="Screen",
                    description="desc",
                    rawImage="raw/root.png",
                    annotatedImages=["annotated/root.png"],
                )
            ]
        )
        # Without _spec_dir, resolves relative to current working directory
        assert spec.resolve_raw_image("raw/root.png") == Path("raw/root.png")
        assert spec.resolve_annotated_image("annotated/root.png") == Path("annotated/root.png")

        # With _spec_dir set
        base_dir = Path("/some/path/to/spec")
        spec._spec_dir = base_dir
        assert spec.resolve_raw_image("raw/root.png") == base_dir / "raw/root.png"
        assert spec.resolve_annotated_image("annotated/root.png") == base_dir / "annotated/root.png"

        # Absolute paths are preserved
        abs_path = "/absolute/image.png"
        import platform
        if platform.system() == "Windows":
            abs_path = "C:\\absolute\\image.png"
        assert spec.resolve_raw_image(abs_path) == Path(abs_path)
