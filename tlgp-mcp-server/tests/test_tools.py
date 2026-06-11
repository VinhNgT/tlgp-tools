"""Tests for MCP tools: prepare_analysis, update_analysis, finalize."""

from __future__ import annotations

import json
import os

import pytest

from tlgp_mcp_server.tools.prepare_analysis import prepare_analysis_impl
from tlgp_mcp_server.tools.update_analysis import update_analysis_impl
from tlgp_mcp_server.tools.finalize import finalize_impl
from tlgp_mcp_server.tools.launch_annotator import launch_annotator_impl


# ============================================================
# Helpers
# ============================================================


def _create_annotation_export(tmp_path, screen_name="Test_Screen"):
    """Create a minimal annotation export structure."""
    screen_dir = tmp_path / screen_name
    screen_dir.mkdir()

    annotation = {
        "screen_name": "Test Screen",
        "description": "Màn hình test",
        "original_image": "test.png",
        "image_width": 1080,
        "image_height": 1920,
        "components": [
            {
                "id": 1,
                "label": "Header",
                "bounds": {"left": 0, "top": 0, "right": 1080, "bottom": 200},
                "children": [
                    {
                        "id": 2,
                        "label": "Back",
                        "bounds": {"left": 0, "top": 0, "right": 50, "bottom": 50},
                        "children": [],
                    },
                    {
                        "id": 3,
                        "label": "Title",
                        "bounds": {"left": 50, "top": 0, "right": 500, "bottom": 50},
                        "children": [],
                    },
                ],
            },
            {
                "id": 4,
                "label": "Banner",
                "bounds": {"left": 0, "top": 200, "right": 1080, "bottom": 600},
                "children": [],
            },
        ],
    }

    json_path = screen_dir / f"{screen_name}.json"
    json_path.write_text(
        json.dumps(annotation, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Create a valid 1x1 white PNG (python-docx validates PNG chunks strictly)
    from PIL import Image as PILImage
    import io

    buf = io.BytesIO()
    PILImage.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    img_path = screen_dir / f"{screen_name}_annotated.png"
    img_path.write_bytes(png_bytes)

    # Create a dummy component image
    comp_img = screen_dir / f"{screen_name}_1_annotated.png"
    comp_img.write_bytes(png_bytes)

    return screen_dir, json_path


def _create_analysis_json(screen_dir, extra_fields=None):
    """Create a minimal analysis.json in the screen directory."""
    analysis = {
        "sectionPrefix": "1.1",
        "exportDir": str(screen_dir),
        "components": [
            {
                "id": 1,
                "label": "Header",
                "description": "",
                "isLeaf": False,
                "imageFile": f"{screen_dir.name}_1_annotated.png",
                "children": [
                    {
                        "stt": 1,
                        "label": "Back",
                        "controlType": "",
                        "required": "",
                        "maxLength": "",
                        "editable": "",
                        "description": "",
                    },
                    {
                        "stt": 2,
                        "label": "Title",
                        "controlType": "",
                        "required": "",
                        "maxLength": "",
                        "editable": "",
                        "description": "",
                    },
                ],
                "interactions": [],
            },
            {
                "id": 4,
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
            "imageFiles": [f"{screen_dir.name}_annotated.png"],
            "topLevelChildren": [
                {
                    "stt": 1,
                    "label": "Header",
                    "controlType": "",
                    "required": "",
                    "maxLength": "",
                    "editable": "",
                    "description": "",
                },
                {
                    "stt": 2,
                    "label": "Banner",
                    "controlType": "",
                    "required": "",
                    "maxLength": "",
                    "editable": "",
                    "description": "",
                },
            ],
            "interactions": [],
        },
        "apis": [],
        "discrepancies": [],
    }
    if extra_fields:
        analysis.update(extra_fields)

    path = screen_dir / "analysis.json"
    path.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ── prepare_analysis ──────────────────────────────────────────


class TestPrepareAnalysis:
    def test_needs_annotation_nonexistent_dir(self, tmp_path):
        result = prepare_analysis_impl(str(tmp_path / "nope"))
        assert result["status"] == "needs_annotation"

    def test_needs_annotation_empty_dir(self, tmp_path):
        result = prepare_analysis_impl(str(tmp_path))
        assert result["status"] == "needs_annotation"

    def test_scaffolds_analysis_json(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        assert result["status"] == "ready"
        assert result["screen_name"] == "Test Screen"
        assert (screen_dir / "analysis.json").exists()

    def test_returns_components_summary(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        # Only non-leaf components in summary
        assert len(result["components"]) == 1
        assert result["components"][0]["label"] == "Header"
        assert result["components"][0]["children_count"] == 2
        assert result["components"][0]["children_labels"] == ["Back", "Title"]

    def test_returns_image_files(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        assert len(result["image_files"]) >= 1

    def test_returns_to_fill_list(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        assert "apis" in result["to_fill"]
        assert any("controlType" in f for f in result["to_fill"])

    def test_returns_schema_inline(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        assert "schema" in result
        assert "sectionPrefix" in result["schema"]

    def test_returns_control_types_inline(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path))

        assert "control_types" in result
        assert "Button" in result["control_types"]

    def test_existing_analysis_returns_ready(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        _create_analysis_json(screen_dir)

        result = prepare_analysis_impl(str(tmp_path))
        assert result["status"] == "ready"

    def test_existing_docx_returns_complete(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        _create_analysis_json(screen_dir)
        (screen_dir / "output.docx").write_bytes(b"fake-docx")

        result = prepare_analysis_impl(str(tmp_path))
        assert result["status"] == "complete"

    def test_custom_section_prefix(self, tmp_path):
        _create_annotation_export(tmp_path)
        result = prepare_analysis_impl(str(tmp_path), section_prefix="2.3")

        analysis_path = result["analysis_path"]
        data = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
        assert data["sectionPrefix"] == "2.3"

    def test_self_as_screen_dir(self, tmp_path):
        """When output_dir itself is the screen dir."""
        screen_name = tmp_path.name
        annotation = {
            "screen_name": "Direct Screen",
            "description": "Test",
            "components": [],
        }
        json_path = tmp_path / f"{screen_name}.json"
        json_path.write_text(json.dumps(annotation), encoding="utf-8")

        result = prepare_analysis_impl(str(tmp_path))
        assert result["status"] == "ready"
        assert result["screen_name"] == "Direct Screen"


# Import Path for the custom prefix test
from pathlib import Path


# ── update_analysis ───────────────────────────────────────────


class TestUpdateAnalysis:
    def test_set_component_description(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[0].description", "value": "Tiêu đề màn hình"},
        ])

        assert result["success"] is True
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert data["components"][0]["description"] == "Tiêu đề màn hình"

    def test_set_child_control_type(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[0].children[0].controlType", "value": "Icon"},
        ])

        assert result["success"] is True
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert data["components"][0]["children"][0]["controlType"] == "Icon"

    def test_batch_updates(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[0].description", "value": "Header"},
            {"path": "components[0].children[0].controlType", "value": "Icon"},
            {"path": "components[0].children[0].description", "value": "Quay lại"},
            {"path": "components[0].children[1].controlType", "value": "Text"},
            {"path": "components[0].children[1].description", "value": "Tên màn hình"},
        ])

        assert result["success"] is True
        assert result["updates_count"] == 5

    def test_set_interactions(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[0].interactions", "value": [
                {"action": "Click Back", "reaction": "Quay về"},
            ]},
        ])

        assert result["success"] is True
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert len(data["components"][0]["interactions"]) == 1

    def test_set_apis(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "apis", "value": [
                {
                    "number": 1,
                    "method": "GET",
                    "title": "List",
                    "url": "/api/list",
                },
            ]},
        ])

        assert result["success"] is True
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert len(data["apis"]) == 1
        assert data["apis"][0]["method"] == "GET"

    def test_set_screen_interactions(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "screen.interactions", "value": [
                {"action": "Khởi động", "reaction": "Gọi API"},
            ]},
        ])

        assert result["success"] is True

    def test_set_discrepancies(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "discrepancies", "value": [
                {
                    "location": "Header",
                    "imageObservation": "Share button visible",
                    "codeObservation": "No handler",
                },
            ]},
        ])

        assert result["success"] is True
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert len(data["discrepancies"]) == 1

    def test_returns_summary(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[0].description", "value": "Header"},
        ])

        assert "summary" in result
        assert "components_with_description" in result["summary"]

    def test_invalid_path_returns_error(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "nonexistent.field", "value": "x"},
        ])

        assert "error" in result

    def test_missing_path_key_returns_error(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"value": "x"},
        ])

        assert "error" in result

    def test_file_not_found(self):
        result = update_analysis_impl("/nonexistent/file.json", [])
        assert "error" in result

    def test_out_of_bounds_index_returns_error(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = update_analysis_impl(str(analysis_path), [
            {"path": "components[99].description", "value": "x"},
        ])

        assert "error" in result


# ── finalize ──────────────────────────────────────────────────


class TestFinalize:
    def test_valid_generates_docx(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = finalize_impl(str(analysis_path))

        assert result["valid"] is True
        assert "output_path" in result
        assert result["tables"] > 0
        assert Path(result["output_path"]).exists()

    def test_file_not_found(self):
        result = finalize_impl("/nonexistent/analysis.json")
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_invalid_json_syntax(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json", encoding="utf-8")
        result = finalize_impl(str(bad_json))
        assert result["valid"] is False

    def test_schema_violation(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"sectionPrefix": "1.1"}', encoding="utf-8")
        result = finalize_impl(str(bad))
        assert result["valid"] is False

    def test_missing_image_is_error(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        # Remove a referenced image
        (screen_dir / f"{screen_dir.name}_1_annotated.png").unlink()

        result = finalize_impl(str(analysis_path))
        assert result["valid"] is False
        assert any("image not found" in e for e in result["errors"])

    def test_warnings_for_empty_fields(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = finalize_impl(str(analysis_path))
        assert result["valid"] is True
        # Should have warnings about empty descriptions, controlTypes, no APIs
        assert len(result["warnings"]) > 0

    def test_discrepancy_warnings(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        # Add a discrepancy via update
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        data["discrepancies"] = [{
            "location": "Header",
            "imageObservation": "Share visible",
            "codeObservation": "No handler",
        }]
        analysis_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        result = finalize_impl(str(analysis_path))
        assert result["valid"] is True
        assert any("Discrepancy" in w for w in result["warnings"])

    def test_custom_output_path(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        custom_out = tmp_path / "custom_output.docx"
        result = finalize_impl(str(analysis_path), str(custom_out))

        assert result["valid"] is True
        assert result["output_path"] == str(custom_out)
        assert custom_out.exists()

    def test_success_message(self, tmp_path):
        screen_dir, _ = _create_annotation_export(tmp_path)
        analysis_path = _create_analysis_json(screen_dir)

        result = finalize_impl(str(analysis_path))
        assert "message" in result
        assert "successfully" in result["message"]


# ── launch_annotator ──────────────────────────────────────────


class TestLaunchAnnotator:
    def test_creates_output_dir(self, tmp_path):
        target = tmp_path / "new_dir"
        result = launch_annotator_impl(str(target))
        assert os.path.isdir(target)
        assert "pid" in result
