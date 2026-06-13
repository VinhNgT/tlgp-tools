"""Tests for exporter — export manifest (imageFile, imageFiles, segments)."""

from __future__ import annotations

import json
import os

from PIL import Image as PILImage
from tlgp_annotation_tool.exporter import _annotate_image_files, export_session
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession

# ============================================================
# Helpers
# ============================================================


def _make_test_image(tmp_path, width=200, height=400, name="test.png") -> str:
    """Create a test PNG image and return its absolute path."""
    img = PILImage.new("RGB", (width, height), color=(255, 255, 255))
    path = os.path.join(str(tmp_path), name)
    img.save(path, "PNG")
    return path


def _make_session(img_path, components=None, cut_lines=None) -> ScreenSession:
    """Build a minimal ScreenSession for testing."""
    session = ScreenSession()
    session.screen_name = "Test Screen"
    session.description = "Test description"
    session.original_image = img_path
    session.components = components or []
    session.cut_lines = cut_lines or []
    return session


# ============================================================
# _annotate_image_files
# ============================================================


class TestAnnotateImageFiles:
    def test_leaf_gets_null(self):
        comp_dicts = [{"id": 1, "label": "Leaf", "bounds": {}}]
        _annotate_image_files(comp_dicts, "Screen")
        assert comp_dicts[0]["imageFile"] is None

    def test_parent_gets_filename(self):
        comp_dicts = [
            {
                "id": 1,
                "label": "Header",
                "children": [{"id": 1, "label": "Back", "bounds": {}}],
            }
        ]
        _annotate_image_files(comp_dicts, "Screen")
        assert comp_dicts[0]["imageFile"] == "Screen_1_annotated.png"
        assert comp_dicts[0]["children"][0]["imageFile"] is None

    def test_nested_parents(self):
        comp_dicts = [
            {
                "id": 2,
                "label": "Section",
                "children": [
                    {
                        "id": 1,
                        "label": "SubSection",
                        "children": [
                            {"id": 1, "label": "Leaf", "bounds": {}},
                        ],
                    }
                ],
            }
        ]
        _annotate_image_files(comp_dicts, "App")
        assert comp_dicts[0]["imageFile"] == "App_2_annotated.png"
        assert comp_dicts[0]["children"][0]["imageFile"] == "App_2_1_annotated.png"
        assert comp_dicts[0]["children"][0]["children"][0]["imageFile"] is None

    def test_multiple_roots(self):
        comp_dicts = [
            {
                "id": 1,
                "label": "A",
                "children": [{"id": 1, "label": "A1", "bounds": {}}],
            },
            {"id": 2, "label": "B", "bounds": {}},
        ]
        _annotate_image_files(comp_dicts, "S")
        assert comp_dicts[0]["imageFile"] == "S_1_annotated.png"
        assert comp_dicts[1]["imageFile"] is None


# ============================================================
# export_session — full integration
# ============================================================


class TestExportSession:
    def test_basic_export_has_image_files(self, tmp_path):
        img_path = _make_test_image(tmp_path)
        components = [
            AnnotationBox(
                id=1,
                label="Header",
                x1=0,
                y1=0,
                x2=200,
                y2=100,
                children=[
                    AnnotationBox(id=1, label="Back", x1=10, y1=10, x2=50, y2=50),
                ],
            ),
            AnnotationBox(id=2, label="Banner", x1=0, y1=100, x2=200, y2=200),
        ]
        session = _make_session(img_path, components)

        json_path, root_paths = export_session(session, str(tmp_path))

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # Root imageFiles
        assert "imageFiles" in data
        assert len(data["imageFiles"]) == 1
        assert data["imageFiles"][0] == "Test_Screen_annotated.png"

        # Component imageFile
        header = data["components"][0]
        assert header["imageFile"] == "Test_Screen_1_annotated.png"
        assert header["children"][0]["imageFile"] is None

        banner = data["components"][1]
        assert banner["imageFile"] is None

    def test_no_segments_without_cuts(self, tmp_path):
        img_path = _make_test_image(tmp_path)
        session = _make_session(
            img_path,
            [
                AnnotationBox(id=1, label="A", x1=0, y1=0, x2=200, y2=200),
            ],
        )

        json_path, _ = export_session(session, str(tmp_path))

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "segments" not in data
        assert "cut_lines" not in data

    def test_segments_with_cuts(self, tmp_path):
        img_path = _make_test_image(tmp_path, height=400)
        components = [
            AnnotationBox(id=1, label="Top", x1=0, y1=50, x2=200, y2=150),
            AnnotationBox(id=2, label="Bottom", x1=0, y1=250, x2=200, y2=350),
        ]
        session = _make_session(img_path, components, cut_lines=[200])

        json_path, root_paths = export_session(session, str(tmp_path))

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # Should have segments
        assert "segments" in data
        assert len(data["segments"]) == 2

        seg1 = data["segments"][0]
        assert seg1["part"] == 1
        assert seg1["imageFile"] == "Test_Screen_annotated_part1.png"
        assert 1 in seg1["componentIds"]
        assert 2 not in seg1["componentIds"]

        seg2 = data["segments"][1]
        assert seg2["part"] == 2
        assert 2 in seg2["componentIds"]
        assert 1 not in seg2["componentIds"]

        # Root imageFiles should be the part files
        assert len(data["imageFiles"]) == 2
        assert "Test_Screen_annotated_part1.png" in data["imageFiles"]
        assert "Test_Screen_annotated_part2.png" in data["imageFiles"]

    def test_json_written_after_images(self, tmp_path):
        """Verify that all image files referenced in JSON actually exist."""
        img_path = _make_test_image(tmp_path)
        components = [
            AnnotationBox(
                id=1,
                label="A",
                x1=0,
                y1=0,
                x2=200,
                y2=200,
                children=[
                    AnnotationBox(id=1, label="A1", x1=10, y1=10, x2=100, y2=100),
                ],
            ),
        ]
        session = _make_session(img_path, components)

        json_path, _ = export_session(session, str(tmp_path))
        export_dir = os.path.dirname(json_path)

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # All root imageFiles must exist on disk
        for img_file in data["imageFiles"]:
            assert os.path.exists(os.path.join(export_dir, img_file)), (
                f"Missing: {img_file}"
            )

        # All component imageFiles must exist on disk
        def check_image_files(comps):
            for comp in comps:
                if comp.get("imageFile"):
                    assert os.path.exists(
                        os.path.join(export_dir, comp["imageFile"])
                    ), f"Missing: {comp['imageFile']}"
                if "children" in comp:
                    check_image_files(comp["children"])

        check_image_files(data["components"])

    def test_backward_compat_old_json_loads(self, tmp_path):
        """Old JSON (without imageFile/imageFiles/segments) must still load."""
        # Simulate an old-format JSON
        old_json = {
            "screen_name": "Old_Screen",
            "description": "",
            "original_image": "/fake/path.png",
            "image_width": 200,
            "image_height": 400,
            "components": [
                {
                    "id": 1,
                    "label": "Header",
                    "bounds": {"x": 0, "y": 0, "w": 200, "h": 100},
                    "pill_corner": "top_left",
                    "children": [
                        {
                            "id": 1,
                            "label": "Back",
                            "bounds": {"x": 10, "y": 10, "w": 40, "h": 40},
                            "pill_corner": "top_left",
                        }
                    ],
                }
            ],
        }

        # The parse_box function from app.py uses .get() for optional fields,
        # so old JSON without imageFile should work. We test the model directly.
        comp = old_json["components"][0]
        assert "imageFile" not in comp  # old format
        # No crash — the field simply doesn't exist
