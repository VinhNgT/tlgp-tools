"""Tests for MCP tools: launch_annotator and generate_spec_doc."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from tlgp_mcp_server.tools.generate_spec_doc import generate_spec_doc_impl
from tlgp_mcp_server.tools.launch_annotator import launch_annotator_impl


# ============================================================
# Helpers
# ============================================================


def _make_png_bytes() -> bytes:
    """Create a valid 1x1 white PNG for image validation tests."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _create_export_dir(tmp_path, screen_name="Test_Screen") -> Path:
    """Create a minimal annotation export directory with images."""
    screen_dir = tmp_path / screen_name
    screen_dir.mkdir()

    png_bytes = _make_png_bytes()

    # Root annotated image
    (screen_dir / f"{screen_name}_annotated.png").write_bytes(png_bytes)
    # Component 1 annotated image
    (screen_dir / f"{screen_name}_1_annotated.png").write_bytes(png_bytes)

    return screen_dir


def _build_analysis(screen_dir: Path) -> dict:
    """Build a minimal valid analysis dict for testing."""
    screen_name = screen_dir.name
    return {
        "sectionPrefix": "1.1",
        "exportDir": str(screen_dir),
        "components": [
            {
                "id": 1,
                "label": "Header",
                "description": "Thanh tiêu đề",
                "isLeaf": False,
                "imageFile": f"{screen_name}_1_annotated.png",
                "children": [
                    {
                        "stt": 1,
                        "label": "Back",
                        "controlType": "Icon",
                        "required": "",
                        "maxLength": "",
                        "editable": "",
                        "description": "Nút quay lại",
                    },
                    {
                        "stt": 2,
                        "label": "Title",
                        "controlType": "Text",
                        "required": "",
                        "maxLength": "",
                        "editable": "",
                        "description": "Tên màn hình",
                    },
                ],
                "interactions": [
                    {"action": "Click Back", "reaction": "Quay về"},
                ],
            },
            {
                "id": 2,
                "label": "Banner",
                "description": "",
                "isLeaf": True,
                "imageFile": None,
                "children": [],
                "interactions": [],
            },
        ],
        "screen": {
            "name": "Test Screen",
            "description": "Màn hình test",
            "imageFiles": [f"{screen_name}_annotated.png"],
            "topLevelChildren": [
                {
                    "stt": 1,
                    "label": "Header",
                    "controlType": "Component",
                    "required": "",
                    "maxLength": "",
                    "editable": "",
                    "description": "Thanh tiêu đề",
                },
                {
                    "stt": 2,
                    "label": "Banner",
                    "controlType": "Image",
                    "required": "",
                    "maxLength": "",
                    "editable": "",
                    "description": "Ảnh banner",
                },
            ],
            "interactions": [],
        },
        "apis": [],
        "discrepancies": [],
    }


# ── generate_spec_doc ─────────────────────────────────────────


class TestGenerateSpecDoc:
    def test_valid_generates_docx(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert "output_path" in result
        assert result["tables"] > 0
        assert Path(result["output_path"]).exists()

    def test_validate_only(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        result = generate_spec_doc_impl(analysis, validate_only=True)

        assert result["valid"] is True
        assert "output_path" not in result
        assert "Validation passed" in result["message"]

    def test_schema_validation_failure(self):
        result = generate_spec_doc_impl({"sectionPrefix": "1.1"})

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_invalid_analysis_type(self):
        result = generate_spec_doc_impl({"components": "not_a_list"})

        assert result["valid"] is False

    def test_missing_image_is_error(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        # Remove the component image
        (screen_dir / f"{screen_dir.name}_1_annotated.png").unlink()

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is False
        assert any("image not found" in e for e in result["errors"])

    def test_missing_screen_image_is_error(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        # Remove the screen image
        (screen_dir / f"{screen_dir.name}_annotated.png").unlink()

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is False
        assert any("Screen image not found" in e for e in result["errors"])

    def test_warnings_for_empty_fields(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        # Clear some fields to trigger warnings
        analysis["components"][0]["children"][0]["controlType"] = ""
        analysis["components"][0]["description"] = ""

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert len(result["warnings"]) > 0

    def test_no_apis_warning(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        result = generate_spec_doc_impl(analysis)

        assert any("No APIs defined" in w for w in result["warnings"])

    def test_discrepancy_warnings(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        analysis["discrepancies"] = [
            {
                "location": "Header",
                "imageObservation": "Share button visible",
                "codeObservation": "No handler",
            },
        ]

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert any("Discrepancy" in w for w in result["warnings"])

    def test_custom_output_path(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        custom_out = tmp_path / "custom_output.docx"
        result = generate_spec_doc_impl(analysis, output_path=str(custom_out))

        assert result["valid"] is True
        assert result["output_path"] == str(custom_out)
        assert custom_out.exists()

    def test_analysis_json_side_effect(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        generate_spec_doc_impl(analysis)

        analysis_json = screen_dir / "analysis.json"
        assert analysis_json.exists()
        saved = json.loads(analysis_json.read_text(encoding="utf-8"))
        assert saved["sectionPrefix"] == "1.1"

    def test_success_message(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        result = generate_spec_doc_impl(analysis)

        assert "message" in result
        assert "successfully" in result["message"]

    def test_nonexistent_export_dir(self, tmp_path):
        analysis = _build_analysis(tmp_path / "nonexistent")

        result = generate_spec_doc_impl(analysis)

        assert result["valid"] is False


# ── launch_annotator ──────────────────────────────────────────


class TestLaunchAnnotator:
    def test_creates_output_dir(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        mock_popen = MagicMock()
        mock_popen.return_value.pid = 12345
        monkeypatch.setattr(
            "tlgp_mcp_server.tools.launch_annotator.subprocess.Popen",
            mock_popen,
        )

        target = tmp_path / "new_dir"
        result = launch_annotator_impl(str(target))
        assert os.path.isdir(target)
        assert result["pid"] == 12345
        mock_popen.assert_called_once()

