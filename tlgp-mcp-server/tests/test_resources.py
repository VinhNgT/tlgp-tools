"""Tests for MCP resources."""

from __future__ import annotations

from tlgp_mcp_server.resources import (
    ANALYSIS_SCHEMA_TEXT,
    CONTROL_TYPES_TEXT,
    get_formatting_spec_text,
)


class TestAnalysisSchema:
    def test_is_nonempty_string(self):
        assert isinstance(ANALYSIS_SCHEMA_TEXT, str)
        assert len(ANALYSIS_SCHEMA_TEXT) > 100

    def test_documents_key_fields(self):
        assert "sectionPrefix" in ANALYSIS_SCHEMA_TEXT
        assert "exportDir" in ANALYSIS_SCHEMA_TEXT
        assert "components" in ANALYSIS_SCHEMA_TEXT
        assert "controlType" in ANALYSIS_SCHEMA_TEXT
        assert "interactions" in ANALYSIS_SCHEMA_TEXT

    def test_distinguishes_pre_filled_and_agent_fields(self):
        assert "Pre-filled?" in ANALYSIS_SCHEMA_TEXT
        assert "✅" in ANALYSIS_SCHEMA_TEXT
        assert "❌" in ANALYSIS_SCHEMA_TEXT


class TestControlTypes:
    def test_is_nonempty_string(self):
        assert isinstance(CONTROL_TYPES_TEXT, str)
        assert len(CONTROL_TYPES_TEXT) > 100

    def test_covers_all_control_types(self):
        expected_types = [
            "Button", "Text", "Icon", "Image",
            "Component", "Tabbar", "Slide",
            "TextField", "Checkbox", "Switch",
        ]
        for ct in expected_types:
            assert ct in CONTROL_TYPES_TEXT, f"Missing control type: {ct}"

    def test_has_classification_rules(self):
        assert "Classification Rules" in CONTROL_TYPES_TEXT


class TestFormattingSpec:
    def test_returns_toml_content(self):
        content = get_formatting_spec_text()
        assert isinstance(content, str)
        assert "font_family" in content
        assert "col_widths_pt" in content

    def test_contains_table_sections(self):
        content = get_formatting_spec_text()
        assert "[table.info]" in content
        assert "[table.ui_elements]" in content
        assert "[table.api]" in content
