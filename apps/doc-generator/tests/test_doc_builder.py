from typing import Any

from doc_generator.doc_builder import build_document
from doc_generator.models import (
    NodeSpec,
    ScreenSpec,
    Api,
    ApiParam,
    Interaction,
    ApiPayload,
)
from PIL import Image
from pathlib import Path


def _minimal_spec(tmp_path, **overrides) -> ScreenSpec:
    """Create a minimal ScreenSpec for testing."""
    screen_apis = overrides.pop("apis", [])
    screen_desc = overrides.pop("screen_description", "Test description")
    screen_name = overrides.pop("screen_name", "Test Screen")
    nodes = overrides.pop("nodes", [])

    # Ensure exactly one screen component (id == 0) exists
    screen_comp = [n for n in nodes if n.id == 0]
    if not screen_comp:
        nodes.append(
            NodeSpec(
                id=0,
                label=screen_name,
                description=screen_desc,
                imageFiles=[],
                childrenIds=[1],
                apis=screen_apis,
            )
        )
        nodes.append(
            NodeSpec(id=1, label="Dummy", controlType="Text")
        )

    defaults = {
        "sectionPrefix": "1.1",
        "imageDir": str(tmp_path),
        "nodes": nodes,
    }
    defaults.update(overrides)

    return ScreenSpec(**defaults)


class TestBuildDocumentMinimal:
    def test_produces_document(self, tmp_path):
        analysis = _minimal_spec(tmp_path)
        doc = build_document(analysis)
        assert hasattr(doc, "paragraphs")
        assert hasattr(doc, "tables")
        assert hasattr(doc, "save")

    def test_can_save(self, tmp_path):
        analysis = _minimal_spec(tmp_path)
        doc = build_document(analysis)
        out_path = tmp_path / "output.docx"
        doc.save(str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_has_screen_heading(self, tmp_path):
        analysis = _minimal_spec(tmp_path)
        doc = build_document(analysis)
        headings = [
            p
            for p in doc.paragraphs
            if p.style is not None
            and p.style.name is not None
            and p.style.name.startswith("Heading")
        ]
        assert len(headings) >= 1
        screen_headings = [h for h in headings if "Test Screen" in h.text]
        assert len(screen_headings) >= 1

    def test_default_font_is_times_new_roman(self, tmp_path):
        analysis = _minimal_spec(tmp_path)
        doc = build_document(analysis)
        normal_style: Any = doc.styles["Normal"]
        assert normal_style.font.name == "Times New Roman"


class TestBuildDocumentWithComponents:
    def test_sub_components_generate_sections(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1", "2"],
                ),
                NodeSpec(
                    id="1",
                    label="Header",
                    description="Header component",
                    childrenIds=["3"],
                    interactions=[
                        Interaction(action="Click", reaction="Go back"),
                    ],
                ),
                NodeSpec(
                    id="2",
                    label="Footer",
                    description="Footer component",
                    childrenIds=["4"],
                ),
                NodeSpec(id="3", label="Back", controlType="Icon"),
                NodeSpec(id="4", label="Copyright", controlType="Text"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Component Header" in text
        assert "Component Footer" in text

    def test_component_tables_present(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Nav",
                    description="Nav bar",
                    childrenIds=["2"],
                    interactions=[
                        Interaction(action="Click", reaction="Go back"),
                    ],
                ),
                NodeSpec(id="2", label="Back", controlType="Icon"),
            ],
        )
        doc = build_document(analysis)
        assert len(doc.tables) >= 3

    def test_empty_children_still_shows_heading(self, tmp_path):
        # Note: although validation prevents this in production, we check behavior
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Empty",
                    description="No children",
                    childrenIds=[],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Mô tả chi tiết các thành phần trên màn hình" in text


class TestBuildDocumentWithApis:
    def test_api_section_generated(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            apis=[
                Api(
                    name="GET Products",
                    url="/api/products",
                    requestRootType="ProductsRequest",
                    request=[
                        ApiPayload(
                            type="ProductsRequest",
                            fields=[
                                ApiParam(name="page", type="int"),
                            ],
                        )
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "1. GET Products" in text
        assert "URL: /api/products" in text
        assert "Request Body (ProductsRequest)" in text

    def test_api_with_response_and_sub_dtos(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            apis=[
                Api(
                    name="GET Detail",
                    url="/api/detail",
                    responseRootType="ProductDTO",
                    response=[
                        ApiPayload(
                            type="ProductDTO",
                            fields=[
                                ApiParam(name="id", type="String"),
                                ApiParam(name="price", type="PriceDTO"),
                            ],
                        ),
                        ApiPayload(
                            type="PriceDTO",
                            fields=[ApiParam(name="amount", type="double")],
                        ),
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Response (data = ProductDTO)" in text
        assert "PriceDTO" in text

    def test_multiple_apis(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            apis=[
                Api(name="GET List", url="/api/list"),
                Api(name="POST Create", url="/api/create"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "1. GET List" in text
        assert "2. POST Create" in text

    def test_post_api_shows_request_body_label(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            apis=[
                Api(
                    name="POST Favorite",
                    url="/api/fav",
                    requestRootType="FavoriteProductRequestDTO",
                    request=[
                        ApiPayload(
                            type="FavoriteProductRequestDTO",
                            fields=[
                                ApiParam(name="product_id", type="String"),
                            ],
                        )
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Request Body (FavoriteProductRequestDTO)" in text

    def test_component_apis_under_component_section(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id=0,
                    label="Test Screen",
                    description="Desc",
                    childrenIds=[1],
                ),
                NodeSpec(
                    id=1,
                    label="Header",
                    description="Header component",
                    childrenIds=[2],
                    apis=[
                        Api(
                            name="GET Get Header Data",
                            url="/api/header",
                        ),
                    ],
                ),
                NodeSpec(id=2, label="Back", controlType="Icon"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Component Header" in text
        assert "1. GET Get Header Data" in text


class TestBuildDocumentWithImages:
    def test_missing_image_shows_placeholder(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Nav",
                    description="Nav bar",
                    imageFiles=["nonexistent.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(id="2", label="Back", controlType="Icon"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Image not found" in text

    def test_existing_image_embedded(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.png"
        img.save(str(img_path))

        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Nav",
                    description="Nav bar",
                    imageFiles=["test.png"],
                    childrenIds=["2"],
                ),
                NodeSpec(id="2", label="Back", controlType="Icon"),
            ],
        )
        doc = build_document(analysis)
        inline_shapes = doc.inline_shapes
        assert len(inline_shapes) >= 1

    def test_no_images_still_shows_heading(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Test description",
                    imageFiles=[],
                    childrenIds=["1"],
                ),
                NodeSpec(id="1", label="Dummy", controlType="Text"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Màn hình chức năng" in text

    def test_subsection_numbering_sequential(self, tmp_path):
        analysis = _minimal_spec(tmp_path)
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "1.1 Thông tin chung" in text
        assert "1.2 Màn hình chức năng" in text
        assert "1.3 Mô tả chi tiết các thành phần" in text
        assert "1.4 Xử lý luồng sự kiện" not in text


class TestBuildDocumentSectionNumbering:
    def test_section_prefix_used(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            sectionPrefix="3.2",
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1"],
                ),
                NodeSpec(
                    id="1",
                    label="Header",
                    description="H",
                    childrenIds=["2"],
                ),
                NodeSpec(id="2", label="Back", controlType="Icon"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "3.2.1." in text
        assert "3.2.2." in text

    def test_screen_section_number_follows_components(self, tmp_path):
        analysis = _minimal_spec(
            tmp_path,
            sectionPrefix="1.1",
            nodes=[
                NodeSpec(
                    id="0",
                    label="Test Screen",
                    description="Desc",
                    childrenIds=["1", "2"],
                ),
                NodeSpec(
                    id="1",
                    label="A",
                    description="A",
                    childrenIds=["3"],
                ),
                NodeSpec(
                    id="2",
                    label="B",
                    description="B",
                    childrenIds=["4"],
                ),
                NodeSpec(id="3", label="A1", controlType="Text"),
                NodeSpec(id="4", label="B1", controlType="Text"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        # 2 components -> sections 1.1.1 and 1.1.2
        # Screen -> section 1.1.3
        assert "1.1.3." in text
