"""Orchestrate the full .docx build from analysis.json data."""

from __future__ import annotations

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches

from doc_generator.image_handler import insert_image
from doc_generator.models import AnalysisData, Api, Component, Screen
from doc_generator.style_constants import StyleConfig, load_default_style
from doc_generator.table_builder import (
    build_api_table,
    build_info_table,
    build_interaction_table,
    build_screen_level_info_table,
    build_ui_elements_table,
)

# ============================================================
# Heading helpers
# ============================================================


def _set_run_font(run, style: StyleConfig):
    """Ensure both Latin and East Asian fonts are set."""
    font_name = style.FONT_FAMILY
    run.font.name = font_name
    # Access the underlying XML element to configure the East Asian font property,
    # as python-docx does not provide a public high-level API for this setting.
    rPr = run._element.get_or_add_rPr()  # noqa: SLF001
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(f"<w:rFonts {nsdecls('w')}/>")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)


def _add_h3(doc: Document, text: str, style: StyleConfig):
    """Component title: HEADING_3, bold, #4F81BD."""
    para = doc.add_heading(level=3)
    run = para.add_run(text)
    _set_run_font(run, style)
    run.font.size = style.FONT_SIZE_DEFAULT
    run.font.color.rgb = style.HEADING_COLOR
    run.font.bold = True


def _add_h4(doc: Document, text: str, style: StyleConfig):
    """Sub-section title: HEADING_4, italic, #4F81BD."""
    para = doc.add_heading(level=4)
    run = para.add_run(text)
    _set_run_font(run, style)
    run.font.size = style.FONT_SIZE_DEFAULT
    run.font.color.rgb = style.HEADING_COLOR
    run.font.italic = True
    run.font.bold = False


def _add_bold_text(doc: Document, text: str, style: StyleConfig):
    """Bold normal text (for API headings, request/response labels)."""
    para = doc.add_paragraph()
    run = para.add_run(text)
    _set_run_font(run, style)
    run.font.size = style.FONT_SIZE_DEFAULT
    run.font.bold = True


def _add_normal_text(doc: Document, text: str, style: StyleConfig):
    """Plain normal text (for API URLs, sub-DTO titles)."""
    para = doc.add_paragraph()
    run = para.add_run(text)
    _set_run_font(run, style)
    run.font.size = style.FONT_SIZE_DEFAULT


# ============================================================
# Section builders
# ============================================================


def _add_component_section(
    doc: Document,
    component: Component,
    section_number: str,
    analysis: AnalysisData,
    style: StyleConfig,
):
    """Build a complete component section with all sub-sections."""
    # H3: Component title
    _add_h3(doc, f"{section_number}. Component {component.label}", style)

    # H4: 1. General info
    _add_h4(doc, f"{section_number}.1 Thông tin chung về chức năng", style)
    build_info_table(doc, component.label, component.description, style)

    # H4: 2. Screen image
    _add_h4(doc, f"{section_number}.2 Màn hình chức năng", style)
    if component.imageFile:
        image_path = analysis.resolve_image(component.imageFile)
        insert_image(doc, image_path, full_width=True)

    # H4: 3. UI elements
    if component.children:
        _add_h4(doc, f"{section_number}.3 Mô tả chi tiết các thành phần trên màn hình", style)
        build_ui_elements_table(doc, component.children, style)

    # H4: 4. Interaction events
    if component.interactions:
        step_count = len(component.interactions)
        _add_h4(
            doc,
            f"{section_number}.4 Xử lý luồng sự kiện tương tác ({step_count} bước)",
            style,
        )
        build_interaction_table(doc, component.interactions, style)

    # Render APIs at the end of the component section
    for idx, api in enumerate(component.apis):
        _add_api_section(doc, api, style, idx + 1)


def _add_screen_section(
    doc: Document,
    screen: Screen,
    section_number: str,
    analysis: AnalysisData,
    style: StyleConfig,
):
    """Build the screen overview section."""
    # H3: Screen title
    _add_h3(doc, f"{section_number}. Màn hình {screen.name}", style)

    # H4: 1. General info
    _add_h4(doc, f"{section_number}.1 Thông tin chung về chức năng", style)
    build_screen_level_info_table(doc, screen.name, screen.description, style)

    # H4: 2. Screen image(s)
    _add_h4(doc, f"{section_number}.2 Màn hình chức năng", style)
    for img_file in screen.imageFiles:
        image_path = analysis.resolve_image(img_file)
        insert_image(doc, image_path, full_width=True)

    # H4: 3. UI elements (top-level children)
    if screen.topLevelChildren:
        _add_h4(doc, f"{section_number}.3 Mô tả chi tiết các thành phần trên màn hình", style)
        build_ui_elements_table(doc, screen.topLevelChildren, style)

    # H4: 4. Interaction events
    if screen.interactions:
        step_count = len(screen.interactions)
        _add_h4(
            doc,
            f"{section_number}.4 Xử lý luồng sự kiện tương tác ({step_count} bước)",
            style,
        )
        build_interaction_table(doc, screen.interactions, style)

    # Render APIs at the end of the screen section
    for idx, api in enumerate(screen.apis):
        _add_api_section(doc, api, style, idx + 1)


def _add_api_section(doc: Document, api: Api, style: StyleConfig, api_index: int):
    """Build a single API documentation block."""
    # API title: bold normal text
    _add_bold_text(doc, f"{api_index}. {api.method} {api.title}", style)

    # API URL: plain normal text
    _add_normal_text(doc, f"URL: {api.url}", style)

    # Request section
    if api.requestParams:
        if api.requestBodyType:
            _add_bold_text(doc, f"Request Body ({api.requestBodyType})", style)
        else:
            _add_bold_text(doc, "Request", style)
        build_api_table(doc, api.requestParams, style)
    elif api.requestDescription:
        _add_bold_text(doc, "Request", style)
        _add_normal_text(doc, api.requestDescription, style)

    # Response section
    if api.responseFields:
        response_label = (
            f"Response (data = {api.responseType})" if api.responseType else "Response"
        )
        _add_bold_text(doc, response_label, style)
        build_api_table(doc, api.responseFields, style)
    elif api.responseType:
        _add_bold_text(doc, f"Response (data = {api.responseType})", style)
        if api.responseDescription:
            _add_normal_text(doc, api.responseDescription, style)

    # Sub-DTO tables
    for sub in api.subDtos:
        title = f"{sub.name} fields"
        if sub.fieldRef:
            title += f" ({sub.fieldRef})"
        _add_normal_text(doc, title, style)
        if sub.fields:
            build_api_table(doc, sub.fields, style)


# ============================================================
# Public API
# ============================================================


def build_document(analysis: AnalysisData) -> Document:
    """Build a complete .docx from analysis data.

    Follows the TLGP spec structure:
    1. Non-leaf component sections (in annotation order)
    2. Screen overview section
    3. API documentation
    """
    doc = Document()
    style_config = load_default_style()

    # Set default font
    style = doc.styles["Normal"]
    style.font.name = style_config.FONT_FAMILY
    style.font.size = style_config.FONT_SIZE_DEFAULT

    # Set page margins (1 inch all around)
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Collect non-leaf components for section numbering
    non_leaf_components = [c for c in analysis.components if not c.isLeaf]

    # Component sections
    for i, component in enumerate(non_leaf_components):
        section_num = f"{analysis.sectionPrefix}.{i + 1}"
        _add_component_section(doc, component, section_num, analysis, style_config)

    # Screen overview section
    screen_section_num = f"{analysis.sectionPrefix}.{len(non_leaf_components) + 1}"
    _add_screen_section(doc, analysis.screen, screen_section_num, analysis, style_config)

    return doc
