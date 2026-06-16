"""Tests for doc_builder — end-to-end document generation."""

from doc_generator.doc_builder import build_document
from doc_generator.models import (
    AnalysisData,
    Api,
    ApiParam,
    ChildElement,
    Component,
    Interaction,
    Screen,
    SubDto,
)
from PIL import Image


def _minimal_analysis(tmp_path, **overrides) -> AnalysisData:
    """Create a minimal AnalysisData for testing."""
    screen_apis = overrides.pop("apis", [])
    screen_desc = overrides.pop("screen_description", "Test description")
    screen_name = overrides.pop("screen_name", "Test Screen")
    defaults = {
        "sectionPrefix": "1.1",
        "exportDir": str(tmp_path),
        "screen": Screen(name=screen_name, description=screen_desc, apis=screen_apis),
    }
    defaults.update(overrides)
    return AnalysisData(**defaults)


class TestBuildDocumentMinimal:
    def test_produces_document(self, tmp_path):
        analysis = _minimal_analysis(tmp_path)
        doc = build_document(analysis)
        # Document() returns a docx.document.Document object
        assert hasattr(doc, "paragraphs")
        assert hasattr(doc, "tables")
        assert hasattr(doc, "save")

    def test_can_save(self, tmp_path):
        analysis = _minimal_analysis(tmp_path)
        doc = build_document(analysis)
        out_path = tmp_path / "output.docx"
        doc.save(str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_has_screen_heading(self, tmp_path):
        analysis = _minimal_analysis(tmp_path)
        doc = build_document(analysis)
        # Find paragraphs with heading style
        headings = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert len(headings) >= 1
        # Screen heading should contain "Màn hình Test Screen"
        screen_headings = [h for h in headings if "Test Screen" in h.text]
        assert len(screen_headings) >= 1

    def test_default_font_is_times_new_roman(self, tmp_path):
        analysis = _minimal_analysis(tmp_path)
        doc = build_document(analysis)
        assert doc.styles["Normal"].font.name == "Times New Roman"


class TestBuildDocumentWithComponents:
    def test_non_leaf_components_generate_sections(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(
                    id=1,
                    label="Header",
                    description="Header component",
                    children=[
                        ChildElement(stt=1, label="Back", controlType="Icon"),
                    ],
                    interactions=[
                        Interaction(action="Click", reaction="Go back"),
                    ],
                ),
                Component(
                    id=2,
                    label="Footer",
                    description="Footer component",
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Component Header" in text
        assert "Component Footer" in text

    def test_leaf_components_skipped(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(id=1, label="Visible", isLeaf=False),
                Component(id=2, label="Hidden Leaf", isLeaf=True),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Visible" in text
        assert "Hidden Leaf" not in text

    def test_component_tables_present(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(
                    id=1,
                    label="Nav",
                    description="Nav bar",
                    children=[
                        ChildElement(stt=1, label="Back", controlType="Icon"),
                    ],
                    interactions=[
                        Interaction(action="Click", reaction="Go back"),
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        # Should have at least: info table + UI table + interaction table
        assert len(doc.tables) >= 3

    def test_no_children_skips_ui_table(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(id=1, label="Empty", description="No children"),
            ],
        )
        doc = build_document(analysis)
        # Only info table for the component + screen tables
        # No UI elements table for the component
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Mô tả chi tiết các thành phần" not in text.split("Màn hình")[0]


class TestBuildDocumentWithApis:
    def test_api_section_generated(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(
                    number=1,
                    method="GET",
                    title="Products",
                    url="/api/products",
                    requestParams=[
                        ApiParam(name="page", dataType="int"),
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "1. GET Products" in text
        assert "URL: /api/products" in text
        assert "Request" in text

    def test_api_with_response_and_sub_dtos(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(
                    number=1,
                    method="GET",
                    title="Detail",
                    url="/api/detail",
                    responseType="ProductDTO",
                    responseFields=[
                        ApiParam(name="id", dataType="String"),
                    ],
                    subDtos=[
                        SubDto(
                            name="PriceDTO",
                            fieldRef="prices",
                            fields=[ApiParam(name="amount", dataType="double")],
                        ),
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Response (data = ProductDTO)" in text
        assert "PriceDTO fields (prices)" in text

    def test_multiple_apis(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(number=1, method="GET", title="List", url="/api/list"),
                Api(number=2, method="POST", title="Create", url="/api/create"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "1. GET List" in text
        assert "2. POST Create" in text

    def test_post_api_shows_request_body_label(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(
                    number=1,
                    method="POST",
                    title="Favorite",
                    url="/api/fav",
                    requestBodyType="FavoriteProductRequestDTO",
                    requestParams=[
                        ApiParam(name="product_id", dataType="String"),
                    ],
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Request Body (FavoriteProductRequestDTO)" in text
        assert "Request\n" not in text  # should NOT have plain "Request"

    def test_free_text_request_description(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(
                    number=1,
                    method="GET",
                    title="Health",
                    url="/api/health",
                    requestDescription="Không có tham số",
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Request" in text
        assert "Không có tham số" in text

    def test_free_text_response_description(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            apis=[
                Api(
                    number=1,
                    method="GET",
                    title="Count",
                    url="/api/count",
                    responseType="int",
                    responseDescription="Tổng số items trong giỏ hàng",
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Response (data = int)" in text
        assert "Tổng số items trong giỏ hàng" in text

    def test_component_apis_under_component_section(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(
                    id=1,
                    label="Header",
                    description="Header component",
                    apis=[
                        Api(number=1, method="GET", title="Get Header Data", url="/api/header"),
                    ]
                )
            ]
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Component Header" in text
        assert "1. GET Get Header Data" in text


class TestBuildDocumentWithImages:
    def test_missing_image_shows_placeholder(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(
                    id=1,
                    label="Nav",
                    description="Nav bar",
                    imageFile="nonexistent.png",
                ),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Image not found" in text

    def test_existing_image_embedded(self, tmp_path):
        # Create a minimal 1x1 PNG

        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.png"
        img.save(str(img_path))

        analysis = _minimal_analysis(
            tmp_path,
            components=[
                Component(
                    id=1,
                    label="Nav",
                    description="Nav bar",
                    imageFile="test.png",
                ),
            ],
        )
        doc = build_document(analysis)
        # Check that an inline shape (image) was added
        inline_shapes = doc.inline_shapes
        assert len(inline_shapes) >= 1


class TestBuildDocumentSectionNumbering:
    def test_section_prefix_used(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            sectionPrefix="3.2",
            components=[
                Component(id=1, label="Header", description="H"),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "3.2.1." in text  # component section
        assert "3.2.2." in text  # screen section

    def test_screen_section_number_follows_components(self, tmp_path):
        analysis = _minimal_analysis(
            tmp_path,
            sectionPrefix="1.1",
            components=[
                Component(id=1, label="A", description="A"),
                Component(id=2, label="B", description="B"),
                Component(id=3, label="C", description="C", isLeaf=True),
            ],
        )
        doc = build_document(analysis)
        text = "\n".join(p.text for p in doc.paragraphs)
        # 2 non-leaf components → sections 1.1.1 and 1.1.2
        # Screen → section 1.1.3
        assert "1.1.3." in text
