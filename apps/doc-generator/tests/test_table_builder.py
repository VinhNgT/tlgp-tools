"""Tests for table_builder — verifies table structure and styling."""

import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from doc_generator.models import (
    ApiParam,
    ChildElement,
    Interaction,
)
from doc_generator.style_constants import (
    BORDER_COLOR_HEX,
    HEADER_BG_HEX,
    INFO_COLS_PT,
    UI_COLS_PT,
    INTERACTION_COLS_PT,
    API_COLS_PT,
    SPACE_AFTER_TABLE_PT,
)
from doc_generator.table_builder import (
    build_api_table,
    build_info_table,
    build_interaction_table,
    build_screen_level_info_table,
    build_ui_elements_table,
)


def _get_cell_shading(cell) -> str | None:
    """Extract the fill color from a cell's shading element."""
    tc = cell._tc
    tcPr = tc.find(qn("w:tcPr"))
    if tcPr is None:
        return None
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.get(qn("w:fill"))


def _get_cell_border_color(cell, edge: str) -> str | None:
    """Extract a border color from a cell."""
    tc = cell._tc
    tcPr = tc.find(qn("w:tcPr"))
    if tcPr is None:
        return None
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        return None
    el = borders.find(qn(f"w:{edge}"))
    if el is None:
        return None
    return el.get(qn("w:color"))


# ── Info Table ────────────────────────────────────────────────────────


class TestInfoTable:
    def test_dimensions(self):
        doc = Document()
        table = build_info_table(doc, "Header", "Description text")
        assert len(table.rows) == 2
        assert len(table.columns) == 2

    def test_header_content(self):
        doc = Document()
        table = build_info_table(doc, "Tiêu đề", "Mô tả...")
        assert table.cell(0, 0).text == "Tên chức năng"
        assert "Tiêu đề" in table.cell(0, 1).text

    def test_data_content(self):
        doc = Document()
        table = build_info_table(doc, "X", "Detailed description")
        assert table.cell(1, 0).text == "Mô tả"
        assert table.cell(1, 1).text == "Detailed description"

    def test_header_row_has_background(self):
        doc = Document()
        table = build_info_table(doc, "A", "B")
        # Both header cells should have F2F2F2 background
        assert _get_cell_shading(table.cell(0, 0)) == HEADER_BG_HEX
        assert _get_cell_shading(table.cell(0, 1)) == HEADER_BG_HEX

    def test_borders_applied(self):
        doc = Document()
        table = build_info_table(doc, "A", "B")
        for row in table.rows:
            for cell in row.cells:
                assert _get_cell_border_color(cell, "top") == BORDER_COLOR_HEX
                assert _get_cell_border_color(cell, "bottom") == BORDER_COLOR_HEX


# ── Screen Level Info Table ───────────────────────────────────────────


class TestScreenLevelInfoTable:
    def test_screen_name_in_header(self):
        doc = Document()
        table = build_screen_level_info_table(doc, "Chi tiết SP", "Desc")
        assert "Chi tiết SP" in table.cell(0, 1).text

    def test_first_col_header(self):
        doc = Document()
        table = build_screen_level_info_table(doc, "X", "Y")
        assert table.cell(0, 0).text == "Tên màn hình"



# ── UI Elements Table ─────────────────────────────────────────────────


class TestUiElementsTable:
    def test_correct_dimensions(self):
        doc = Document()
        children = [
            ChildElement(stt=1, label="Back", controlType="Icon"),
            ChildElement(stt=2, label="Title", controlType="Text"),
        ]
        table = build_ui_elements_table(doc, children)
        assert len(table.rows) == 3  # 1 header + 2 data
        assert len(table.columns) == 7

    def test_header_labels(self):
        doc = Document()
        children = [ChildElement(stt=1, label="A", controlType="B")]
        table = build_ui_elements_table(doc, children)
        headers = [table.cell(0, c).text for c in range(7)]
        assert headers[0] == "STT"
        assert headers[1] == "Tên"
        assert headers[6] == "Mô tả"

    def test_data_populated(self):
        doc = Document()
        children = [
            ChildElement(
                stt=1, label="Share", controlType="Icon",
                description="Share product",
            ),
        ]
        table = build_ui_elements_table(doc, children)
        assert table.cell(1, 0).text == "1"
        assert table.cell(1, 1).text == "Share"
        assert table.cell(1, 2).text == "Icon"
        assert table.cell(1, 6).text == "Share product"

    def test_empty_children_produces_header_only(self):
        doc = Document()
        table = build_ui_elements_table(doc, [])
        assert len(table.rows) == 1  # header only


# ── Interaction Table ─────────────────────────────────────────────────


class TestInteractionTable:
    def test_correct_dimensions(self):
        doc = Document()
        interactions = [
            Interaction(action="Click Back", reaction="Go back"),
        ]
        table = build_interaction_table(doc, interactions)
        assert len(table.rows) == 2  # 1 header + 1 data
        assert len(table.columns) == 2

    def test_header_labels(self):
        doc = Document()
        interactions = [Interaction(action="A", reaction="B")]
        table = build_interaction_table(doc, interactions)
        assert table.cell(0, 0).text == "Hành động của tác nhân"
        assert table.cell(0, 1).text == "Phản ứng của hệ thống"

    def test_data_populated(self):
        doc = Document()
        interactions = [
            Interaction(action="Tap share", reaction="Open share sheet"),
        ]
        table = build_interaction_table(doc, interactions)
        assert table.cell(1, 0).text == "Tap share"
        assert table.cell(1, 1).text == "Open share sheet"


# ── API Table ─────────────────────────────────────────────────────────


class TestApiTable:
    def test_correct_dimensions(self):
        doc = Document()
        params = [
            ApiParam(name="id", meaning="ID", dataType="String"),
        ]
        table = build_api_table(doc, params)
        assert len(table.rows) == 2
        assert len(table.columns) == 6

    def test_header_labels(self):
        doc = Document()
        params = [ApiParam(name="x")]
        table = build_api_table(doc, params)
        headers = [table.cell(0, c).text for c in range(6)]
        assert headers[0] == "Tên tham số"
        assert headers[3] == "Kiểu dữ liệu"

    def test_data_populated(self):
        doc = Document()
        params = [
            ApiParam(
                name="merchant_id", meaning="Mã đối tác",
                required="Có", dataType="String",
            ),
        ]
        table = build_api_table(doc, params)
        assert table.cell(1, 0).text == "merchant_id"
        assert table.cell(1, 1).text == "Mã đối tác"
        assert table.cell(1, 2).text == "Có"
        assert table.cell(1, 3).text == "String"

    def test_multiple_params(self):
        doc = Document()
        params = [
            ApiParam(name="a"),
            ApiParam(name="b"),
            ApiParam(name="c"),
        ]
        table = build_api_table(doc, params)
        assert len(table.rows) == 4  # 1 header + 3 data

    def test_header_has_shading(self):
        doc = Document()
        params = [ApiParam(name="x")]
        table = build_api_table(doc, params)
        for c in range(6):
            assert _get_cell_shading(table.cell(0, c)) == HEADER_BG_HEX


# ── Table Spacing ─────────────────────────────────────────────────────


class TestTableSpacing:
    def test_spacing_added_after_info_table(self):
        doc = Document()
        build_info_table(doc, "Header", "Description")
        # There should be at least one paragraph added for spacing
        spacer_para = doc.paragraphs[-1]
        assert spacer_para.paragraph_format.space_before == Pt(0)
        assert spacer_para.paragraph_format.space_after == Pt(SPACE_AFTER_TABLE_PT)
        assert spacer_para.paragraph_format.line_spacing == Pt(1)

    def test_spacing_added_after_ui_table(self):
        doc = Document()
        build_ui_elements_table(doc, [])
        spacer_para = doc.paragraphs[-1]
        assert spacer_para.paragraph_format.space_before == Pt(0)
        assert spacer_para.paragraph_format.space_after == Pt(SPACE_AFTER_TABLE_PT)
        assert spacer_para.paragraph_format.line_spacing == Pt(1)

