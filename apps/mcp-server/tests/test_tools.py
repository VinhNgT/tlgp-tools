"""Tests for MCP tools, services, and managers."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.server import generate_spec_doc
from mcp_server.services import SpecGeneratorService
from PIL import Image as PILImage

# ============================================================
# Helpers
# ============================================================


def _make_png_bytes() -> bytes:
    """Create a valid 1x1 white PNG for image validation tests."""
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
        "discrepancies": [],
    }


# ── generate_spec_doc ─────────────────────────────────────────


class TestGenerateSpecDoc:
    def test_valid_generates_docx(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert "output_path" in result
        assert result["tables"] > 0
        assert Path(result["output_path"]).exists()

    def test_validate_only(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis, validate_only=True)

        assert result["valid"] is True
        assert "output_path" not in result
        assert result["components"] == 2
        assert result["non_leaf"] == 1
        assert result["ui_elements"] == 2
        assert result["apis"] == 0
        assert result["images"] >= 1

    def test_schema_validation_failure(self):
        service = SpecGeneratorService()
        result = service.generate_spec_doc_impl({"sectionPrefix": "1.1"})

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_invalid_analysis_type(self):
        service = SpecGeneratorService()
        result = service.generate_spec_doc_impl({"components": "not_a_list"})

        assert result["valid"] is False

    def test_missing_image_is_error(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        # Remove the component image
        (screen_dir / f"{screen_dir.name}_1_annotated.png").unlink()

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is False
        assert any("image not found" in e for e in result["errors"])

    def test_missing_screen_image_is_error(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        # Remove the screen image
        (screen_dir / f"{screen_dir.name}_annotated.png").unlink()

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is False
        assert any("Screen image not found" in e for e in result["errors"])

    def test_warnings_for_empty_fields(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        # Clear some fields to trigger warnings
        analysis["components"][0]["children"][0]["controlType"] = ""
        analysis["components"][0]["description"] = ""

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert len(result["warnings"]) > 0

    def test_no_apis_warning(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis)

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
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is True
        assert any("Discrepancy" in w for w in result["warnings"])

    def test_custom_output_path(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        custom_out = tmp_path / "custom_output.docx"
        result = service.generate_spec_doc_impl(analysis, output_path=str(custom_out))

        assert result["valid"] is True
        assert result["output_path"] == str(custom_out)
        assert custom_out.exists()

        # Verify analysis JSON is written alongside the custom docx path
        analysis_json = tmp_path / "analysis.json"
        assert analysis_json.exists()
        saved = json.loads(analysis_json.read_text(encoding="utf-8"))
        assert saved["sectionPrefix"] == "1.1"

    def test_analysis_json_side_effect(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        service.generate_spec_doc_impl(analysis)

        analysis_json = screen_dir / "analysis.json"
        assert analysis_json.exists()
        saved = json.loads(analysis_json.read_text(encoding="utf-8"))
        assert saved["sectionPrefix"] == "1.1"

    def test_no_message_in_response(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis)

        assert "message" not in result
        assert result["valid"] is True

    def test_nonexistent_export_dir(self, tmp_path):
        analysis = _build_analysis(tmp_path / "nonexistent")
        service = SpecGeneratorService()

        result = service.generate_spec_doc_impl(analysis)

        assert result["valid"] is False

    @pytest.mark.anyio
    async def test_generate_with_analysis_path(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)
        service = SpecGeneratorService()

        # Write analysis to file
        analysis_json_file = tmp_path / "test_analysis.json"
        analysis_json_file.write_text(
            json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
        )

        result = await service.generate(analysis_path=str(analysis_json_file))

        assert result["valid"] is True
        assert Path(result["output_path"]).exists()

    @pytest.mark.anyio
    async def test_analysis_path_does_not_exist(self):
        service = SpecGeneratorService()
        result = await service.generate(analysis_path="nonexistent_file.json")

        assert result["valid"] is False
        assert "Failed to read analysis_path" in result["errors"][0]


# ── launch_annotator ──────────────────────────────────────────


class TestLaunchAnnotator:
    @pytest.mark.anyio
    async def test_launch_annotator_success(self, tmp_path, monkeypatch):
        mock_popen = MagicMock()
        mock_popen.return_value.pid = 12345
        monkeypatch.setattr(
            "mcp_server.manager.subprocess.Popen",
            mock_popen,
        )
        monkeypatch.setattr(
            "mcp_server.manager.shutil.which",
            lambda name: "/usr/local/bin/uv",
        )

        # Mock httpx.AsyncClient to avoid actual HTTP calls and timeouts
        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def get(self, url, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.status_code = 200
                return mock_res

            async def post(self, url, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.status_code = 200
                return mock_res

        monkeypatch.setattr(
            "mcp_server.manager.httpx.AsyncClient",
            MockAsyncClient,
        )

        # Create dummy screenshot to pass validation
        screenshot = tmp_path / "test.png"
        screenshot.write_bytes(b"dummy")

        manager = DaemonManager()
        result = await manager.launch_annotator(screenshot_path=str(screenshot))
        assert result["annotator_pid"] == 12345
        assert result["annotator_ready"] is True
        assert mock_popen.call_count == 1

        # Verify uv run is used instead of sys.executable
        for call in mock_popen.call_args_list:
            call_args = call[0][0]
            assert call_args[0] == "/usr/local/bin/uv"
            assert "run" in call_args

    @pytest.mark.anyio
    async def test_raises_when_uv_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mcp_server.manager.shutil.which",
            lambda name: None,
        )

        manager = DaemonManager()
        with pytest.raises(RuntimeError, match="uv is not installed"):
            await manager.launch_annotator(screenshot_path=str(tmp_path / "out"))


class TestWriteAnalysisJson:
    def test_write_success(self, tmp_path):
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        data = {"exportDir": str(export_dir), "test": "data"}

        service = SpecGeneratorService()
        res = service.write_analysis_json(data, "test.json")
        assert res["success"] is True
        assert "analysis_path" in res

        filepath = Path(res["analysis_path"])
        assert filepath.exists()
        assert json.loads(filepath.read_text(encoding="utf-8")) == data

    def test_missing_export_dir(self):
        service = SpecGeneratorService()
        res = service.write_analysis_json({"test": "data"})
        assert res["success"] is False
        assert "Missing 'exportDir'" in res["error"]

    def test_invalid_export_dir(self):
        service = SpecGeneratorService()
        res = service.write_analysis_json({"exportDir": "nonexistent_dir"})
        assert res["success"] is False
        assert "not a valid directory" in res["error"]


class TestDaemonControl:
    @pytest.mark.anyio
    async def test_get_daemon_status(self, monkeypatch):
        manager = DaemonManager()
        manager.active_processes.clear()

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def get(self, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.status_code = 200
                return mock_res

        monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

        status = await manager.get_status()
        assert status["annotator"]["running"] is True

    def test_read_daemon_logs(self):
        manager = DaemonManager()
        manager.annotator_logs.clear()

        manager.annotator_logs.append("line1\n")
        manager.annotator_logs.append("line2\n")

        res = manager.read_daemon_logs("annotator", lines=1)
        assert res["daemon"] == "annotator"
        assert res["line_count"] == 1
        assert res["logs"] == "line2\n"




class TestGenerateSpecDocWrapper:
    @pytest.mark.anyio
    async def test_generate_spec_doc_progress_and_elicitation(self, tmp_path):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        # Force a component description to be empty to trigger elicitation
        analysis["components"][0]["description"] = ""

        # Mock Context
        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.log = AsyncMock()

        # Mock elicitation response
        mock_elicit_result = MagicMock()
        mock_elicit_result.action = "accept"
        mock_elicit_result.data.description = "Elicited Header Description"
        ctx.elicit = AsyncMock(return_value=mock_elicit_result)

        # Call generate_spec_doc wrapper
        result = await generate_spec_doc(
            ctx=ctx, analysis=analysis, output_path=str(tmp_path / "out.docx")
        )

        assert result["valid"] is True

        # Verify progress was reported
        ctx.report_progress.assert_any_call(
            10, 100, "Loading and validating analysis data..."
        )
        ctx.report_progress.assert_any_call(
            30, 100, "Eliciting description for 'Header'..."
        )
        ctx.report_progress.assert_any_call(60, 100, "Running document generation...")
        ctx.report_progress.assert_any_call(100, 100, "Spec generation complete.")

        # Verify elicitation was called
        ctx.elicit.assert_called_once()

        # Verify the description was updated in the resulting doc/JSON
        analysis_json = tmp_path / "analysis.json"
        assert analysis_json.exists()
        saved = json.loads(analysis_json.read_text(encoding="utf-8"))
        assert saved["components"][0]["description"] == "Elicited Header Description"

    @pytest.mark.anyio
    async def test_generate_spec_doc_exports_workspace_zip(self, tmp_path, monkeypatch):
        screen_dir = _create_export_dir(tmp_path)
        analysis = _build_analysis(screen_dir)

        # Mock WorkspaceClient.export_workspace
        async def mock_export_workspace(client_self, output_path: str):
            Path(output_path).write_bytes(b"mock_zip_content")
            return {"status": "success", "output_path": output_path}

        monkeypatch.setattr(WorkspaceClient, "export_workspace", mock_export_workspace)

        # Mock Context
        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.log = AsyncMock()

        # Call generate_spec_doc wrapper
        out_docx = tmp_path / "out.docx"
        result = await generate_spec_doc(
            ctx=ctx, analysis=analysis, output_path=str(out_docx)
        )

        assert result["valid"] is True
        assert out_docx.exists()

        # Verify workspace.zip is exported next to out.docx
        workspace_zip = tmp_path / "workspace.zip"
        assert workspace_zip.exists()
        assert workspace_zip.read_bytes() == b"mock_zip_content"
