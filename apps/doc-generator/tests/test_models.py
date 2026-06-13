"""Tests for Pydantic models — validation, defaults, and image resolution."""

import pytest
import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from doc_generator.models import (
    AnalysisData,
    Api,
    ApiParam,
    ChildElement,
    Component,
    Discrepancy,
    Interaction,
    Screen,
    SubDto,
)


# ── ChildElement ──────────────────────────────────────────────────────


class TestChildElement:
    def test_required_fields(self):
        child = ChildElement(stt=1, label="Button", controlType="Icon")
        assert child.stt == 1
        assert child.label == "Button"
        assert child.controlType == "Icon"

    def test_optional_fields_default_empty(self):
        child = ChildElement(stt=1, label="A", controlType="Text")
        assert child.required == ""
        assert child.maxLength == ""
        assert child.editable == ""
        assert child.description == ""


# ── Interaction ───────────────────────────────────────────────────────


class TestInteraction:
    def test_basic(self):
        i = Interaction(action="Click Back", reaction="Go back")
        assert i.action == "Click Back"
        assert i.reaction == "Go back"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Interaction(action="Click")  # missing reaction


# ── Component ─────────────────────────────────────────────────────────


class TestComponent:
    def test_minimal(self):
        c = Component(id=1, label="Header")
        assert c.isLeaf is False
        assert c.imageFile is None
        assert c.children == []
        assert c.interactions == []

    def test_with_children_and_interactions(self):
        c = Component(
            id=1, label="Header",
            children=[ChildElement(stt=1, label="Back", controlType="Icon")],
            interactions=[Interaction(action="Click", reaction="Go back")],
        )
        assert len(c.children) == 1
        assert len(c.interactions) == 1

    def test_leaf_component(self):
        c = Component(id=1, label="Leaf", isLeaf=True)
        assert c.isLeaf is True


# ── ApiParam ──────────────────────────────────────────────────────────


class TestApiParam:
    def test_required_field_only(self):
        p = ApiParam(name="merchant_id")
        assert p.meaning == ""
        assert p.required == ""
        assert p.dataType == ""

    def test_full_param(self):
        p = ApiParam(
            name="page", meaning="Page number",
            required="Có", dataType="int",
            limit="1-100", defaultValue="1",
        )
        assert p.limit == "1-100"


# ── Api ───────────────────────────────────────────────────────────────


class TestApi:
    def test_minimal(self):
        a = Api(number=1, method="GET", title="Products", url="/api/products")
        assert a.requestParams == []
        assert a.responseFields == []
        assert a.subDtos == []

    def test_with_sub_dtos(self):
        a = Api(
            number=1, method="GET", title="Detail", url="/api/detail",
            subDtos=[
                SubDto(name="PriceTiersDTO", fieldRef="price_tiers", fields=[
                    ApiParam(name="min_qty", dataType="int"),
                ]),
            ],
        )
        assert len(a.subDtos) == 1
        assert a.subDtos[0].fields[0].name == "min_qty"

    def test_request_body_type(self):
        a = Api(
            number=1, method="POST", title="Favorite", url="/api/fav",
            requestBodyType="FavoriteProductRequestDTO",
        )
        assert a.requestBodyType == "FavoriteProductRequestDTO"

    def test_request_body_type_default_empty(self):
        a = Api(number=1, method="GET", title="List", url="/api/list")
        assert a.requestBodyType == ""

    def test_free_text_descriptions(self):
        a = Api(
            number=3, method="GET", title="Cart count", url="/api/cart/count",
            requestDescription="Không có tham số",
            responseType="int",
            responseDescription="Tổng số items trong giỏ hàng",
        )
        assert a.requestDescription == "Không có tham số"
        assert a.responseDescription == "Tổng số items trong giỏ hàng"


# ── Discrepancy ───────────────────────────────────────────────────────


class TestDiscrepancy:
    def test_required_fields(self):
        d = Discrepancy(
            location="Component Header",
            imageObservation="Share button visible",
            codeObservation="No share handler in code",
        )
        assert d.location == "Component Header"
        assert d.resolution == ""

    def test_with_resolution(self):
        d = Discrepancy(
            location="Price component",
            imageObservation="Shows VND price",
            codeObservation="API returns CNY only",
            resolution="Price is converted client-side",
        )
        assert d.resolution == "Price is converted client-side"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            Discrepancy(location="X")  # missing observations


# ── Screen ────────────────────────────────────────────────────────────


class TestScreen:
    def test_defaults(self):
        s = Screen(name="Home")
        assert s.imageFiles == []
        assert s.topLevelChildren == []
        assert s.interactions == []

    def test_with_description(self):
        s = Screen(
            name="Product Detail",
            description="Shows product info",
        )
        assert s.description == "Shows product info"


# ── AnalysisData ──────────────────────────────────────────────────────


class TestAnalysisData:
    def test_valid_with_real_dir(self, tmp_path):
        data = AnalysisData(
            sectionPrefix="1.1",
            exportDir=str(tmp_path),
            screen=Screen(name="Test"),
        )
        assert data.sectionPrefix == "1.1"
        assert data.components == []
        assert data.apis == []
        assert data.discrepancies == []

    def test_invalid_export_dir_raises(self):
        with pytest.raises(ValidationError, match="exportDir does not exist"):
            AnalysisData(
                exportDir="/nonexistent/path/12345",
                screen=Screen(name="Test"),
            )

    def test_resolve_image(self, tmp_path):
        (tmp_path / "test.png").touch()
        data = AnalysisData(
            exportDir=str(tmp_path),
            screen=Screen(name="Test"),
        )
        resolved = data.resolve_image("test.png")
        assert resolved == tmp_path / "test.png"
        assert resolved.exists()

    def test_missing_screen_raises(self):
        with pytest.raises(ValidationError):
            AnalysisData(exportDir="/tmp")  # missing screen

    def test_with_discrepancies(self, tmp_path):
        data = AnalysisData(
            exportDir=str(tmp_path),
            screen=Screen(name="Test"),
            discrepancies=[
                Discrepancy(
                    location="Header",
                    imageObservation="Button visible",
                    codeObservation="No handler",
                ),
            ],
        )
        assert len(data.discrepancies) == 1
        assert data.discrepancies[0].location == "Header"


# ── JSON round-trip ───────────────────────────────────────────────────


class TestJsonRoundTrip:
    def test_load_from_fixture(self, tmp_path):
        """Load the sample analysis.json fixture."""
        fixture_dir = Path(__file__).parent / "fixtures"
        fixture_path = fixture_dir / "sample_analysis.json"

        if not fixture_path.exists():
            pytest.skip("sample_analysis.json fixture not found")

        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        # Override exportDir to use the actual fixture directory
        raw["exportDir"] = str(fixture_dir)
        data = AnalysisData.model_validate(raw)

        assert data.sectionPrefix == "1.1"
        assert data.screen.name == "Chi tiết sản phẩm"
        assert len(data.components) == 2
        assert len(data.apis) == 1
        assert data.apis[0].method == "GET"

    def test_serialize_and_deserialize(self, tmp_path):
        data = AnalysisData(
            sectionPrefix="2.3",
            exportDir=str(tmp_path),
            screen=Screen(name="Cart"),
            components=[
                Component(id=1, label="Header", children=[
                    ChildElement(stt=1, label="Back", controlType="Icon"),
                ]),
            ],
            apis=[
                Api(number=1, method="POST", title="Add to cart", url="/api/cart"),
            ],
        )
        json_str = data.model_dump_json()
        restored = AnalysisData.model_validate_json(json_str)
        assert restored.screen.name == "Cart"
        assert len(restored.components) == 1
        assert restored.components[0].children[0].label == "Back"
