"""Tests for tlgp-mcp-server tools."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from tlgp_mcp_server.tools.list_exports import list_exports_impl
from tlgp_mcp_server.tools.parse_annotations import parse_annotations_impl
from tlgp_mcp_server.tools.scaffold_analysis import scaffold_analysis_impl
from tlgp_mcp_server.tools.validate_analysis import validate_analysis_impl


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_annotation():
    """Minimal annotation tool export JSON."""
    return {
        "screen_name": "TestScreen",
        "description": "A test screen",
        "original_image": "/fake/path/screenshot.png",
        "image_width": 1080,
        "image_height": 2340,
        "cut_lines": [],
        "components": [
            {
                "id": 1,
                "label": "Header",
                "bounds": {"x": 0, "y": 0, "w": 1080, "h": 200},
                "children": [
                    {
                        "id": 2,
                        "label": "Title",
                        "bounds": {"x": 10, "y": 10, "w": 500, "h": 40},
                        "children": [],
                    },
                    {
                        "id": 3,
                        "label": "Back Button",
                        "bounds": {"x": 0, "y": 10, "w": 50, "h": 50},
                        "children": [],
                    },
                ],
            },
            {
                "id": 4,
                "label": "Content",
                "bounds": {"x": 0, "y": 200, "w": 1080, "h": 2000},
                "children": [],
            },
        ],
    }


@pytest.fixture
def export_dir(tmp_path, sample_annotation):
    """Create a realistic annotation export directory structure."""
    screen_dir = tmp_path / "TestScreen"
    screen_dir.mkdir()

    # Write annotation JSON
    json_path = screen_dir / "TestScreen.json"
    json_path.write_text(json.dumps(sample_annotation), encoding="utf-8")

    # Create annotated images
    (screen_dir / "TestScreen_annotated.png").write_bytes(b"fake-png")
    (screen_dir / "TestScreen_1_annotated.png").write_bytes(b"fake-png")

    return tmp_path


# ============================================================
# list_exports tests
# ============================================================


class TestListExports:
    def test_not_found(self, tmp_path):
        result = list_exports_impl(str(tmp_path / "nonexistent"))
        assert result["status"] == "not_found"

    def test_empty_directory(self, tmp_path):
        result = list_exports_impl(str(tmp_path))
        assert result["status"] == "empty"

    def test_annotations_only(self, export_dir):
        result = list_exports_impl(str(export_dir))
        assert result["status"] == "annotations_only"
        assert len(result["screens"]) == 1
        assert result["screens"][0]["screen_name"] == "TestScreen"
        assert result["screens"][0]["annotation_json"] is not None
        assert result["screens"][0]["analysis_json"] is None

    def test_ready_status(self, export_dir, sample_annotation):
        """When analysis.json exists but no .docx."""
        screen_dir = export_dir / "TestScreen"
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(screen_dir),
            "components": [],
            "screen": {
                "name": "TestScreen",
                "description": "test",
            },
        }
        (screen_dir / "analysis.json").write_text(
            json.dumps(analysis), encoding="utf-8"
        )
        result = list_exports_impl(str(export_dir))
        assert result["status"] == "ready"

    def test_complete_status(self, export_dir, sample_annotation):
        """When both analysis.json and .docx exist."""
        screen_dir = export_dir / "TestScreen"
        analysis = {
            "sectionPrefix": "1.1",
            "exportDir": str(screen_dir),
            "components": [],
            "screen": {"name": "TestScreen"},
        }
        (screen_dir / "analysis.json").write_text(
            json.dumps(analysis), encoding="utf-8"
        )
        (screen_dir / "TestScreen.docx").write_bytes(b"fake-docx")
        result = list_exports_impl(str(export_dir))
        assert result["status"] == "complete"

    def test_file_instead_of_dir(self, tmp_path):
        """Path is a file, not a directory."""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("content")
        result = list_exports_impl(str(file_path))
        assert result["status"] == "malformed"


# ============================================================
# parse_annotations tests
# ============================================================


class TestParseAnnotations:
    def test_valid_json(self, export_dir):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        result = parse_annotations_impl(json_path)
        assert "error" not in result
        assert result["screen_name"] == "TestScreen"
        assert result["component_count"] == 2
        assert result["components"][0]["has_children"] is True
        assert result["components"][0]["children_count"] == 2
        assert result["components"][1]["has_children"] is False

    def test_file_not_found(self):
        result = parse_annotations_impl("/nonexistent/file.json")
        assert "error" in result

    def test_invalid_json(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json}")
        result = parse_annotations_impl(str(bad_json))
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_missing_required_fields(self, tmp_path):
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"foo": "bar"}')
        result = parse_annotations_impl(str(incomplete))
        assert "error" in result
        assert "Missing required fields" in result["error"]


# ============================================================
# scaffold_analysis tests
# ============================================================


class TestScaffoldAnalysis:
    def test_generates_template(self, export_dir):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        result = scaffold_analysis_impl(json_path)
        assert "error" not in result
        assert result["screen_name"] == "TestScreen"
        assert result["component_count"] == 2
        assert result["non_leaf_count"] == 1  # Header has children
        assert result["leaf_count"] == 1  # Content is a leaf
        assert Path(result["output_path"]).exists()

        # Verify the generated JSON
        analysis = json.loads(Path(result["output_path"]).read_text())
        assert analysis["sectionPrefix"] == "1.1"
        assert len(analysis["components"]) == 2

        # Header should have children with sequential STT
        header = analysis["components"][0]
        assert header["isLeaf"] is False
        assert len(header["children"]) == 2
        assert header["children"][0]["stt"] == 1
        assert header["children"][1]["stt"] == 2
        assert header["children"][0]["label"] == "Title"

        # Content should be a leaf with no children
        content = analysis["components"][1]
        assert content["isLeaf"] is True
        assert content["children"] == []

    def test_custom_section_prefix(self, export_dir):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        result = scaffold_analysis_impl(json_path, section_prefix="2.3")
        analysis = json.loads(Path(result["output_path"]).read_text())
        assert analysis["sectionPrefix"] == "2.3"

    def test_custom_output_path(self, export_dir, tmp_path):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        custom_out = str(tmp_path / "custom" / "output.json")
        result = scaffold_analysis_impl(json_path, output_path=custom_out)
        assert result["output_path"] == custom_out
        assert Path(custom_out).exists()

    def test_pre_filled_and_to_fill_lists(self, export_dir):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        result = scaffold_analysis_impl(json_path)
        assert len(result["pre_filled"]) > 0
        assert len(result["to_fill"]) > 0
        assert "components[].id" in result["pre_filled"]
        assert "components[].children[].controlType" in result["to_fill"]

    def test_annotation_not_found(self):
        result = scaffold_analysis_impl("/nonexistent/file.json")
        assert "error" in result


# ============================================================
# validate_analysis tests
# ============================================================


class TestValidateAnalysis:
    def test_valid_analysis(self, export_dir):
        """Scaffold and immediately validate should pass."""
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        scaffold_result = scaffold_analysis_impl(json_path)
        result = validate_analysis_impl(scaffold_result["output_path"])

        # Scaffold produces valid schema but with content warnings
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) > 0  # Empty descriptions, controlTypes

    def test_file_not_found(self):
        result = validate_analysis_impl("/nonexistent/analysis.json")
        assert result["valid"] is False
        assert len(result["errors"]) == 1

    def test_invalid_json_syntax(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid}")
        result = validate_analysis_impl(str(bad))
        assert result["valid"] is False
        assert "Invalid JSON" in result["errors"][0]

    def test_schema_violation(self, tmp_path):
        """Missing required 'screen' field."""
        invalid = tmp_path / "invalid.json"
        invalid.write_text(json.dumps({
            "exportDir": str(tmp_path),
            "components": [],
        }))
        result = validate_analysis_impl(str(invalid))
        assert result["valid"] is False
        assert any("screen" in e for e in result["errors"])

    def test_summary_counts(self, export_dir):
        json_path = str(export_dir / "TestScreen" / "TestScreen.json")
        scaffold_result = scaffold_analysis_impl(json_path)
        result = validate_analysis_impl(scaffold_result["output_path"])
        summary = result["summary"]
        assert summary["screen_name"] == "TestScreen"
        assert summary["total_components"] == 2
        assert summary["non_leaf_components"] == 1
        assert summary["leaf_components"] == 1
