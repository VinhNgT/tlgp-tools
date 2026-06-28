"""Tests for MCP prompts."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from mcp_server.prompts import get_spec_workflow
from tlgp_contracts import get_example_spec_json

SPEC_WORKFLOW_CONTENT = ""


@pytest.fixture(autouse=True, scope="module")
def setup_spec_workflow_content():
    global SPEC_WORKFLOW_CONTENT
    SPEC_WORKFLOW_CONTENT = get_spec_workflow()


class TestSpecWorkflowContent:
    def test_is_nonempty(self):
        assert isinstance(SPEC_WORKFLOW_CONTENT, str)
        assert len(SPEC_WORKFLOW_CONTENT) > 100

    def test_references_current_tools(self):
        tools = [
            "launch_annotator",
            "connect_to_annotator",
            "scaffold_spec",
            "update_spec_node",
            "validate_spec",
            "compile_spec",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_CONTENT, f"Missing tool reference: {tool}"

    def test_does_not_reference_old_tools(self):
        old_tools = [
            "prepare_analysis",
            "generate_spec_doc",
            "export_workspace",
            "export_images",
            "scaffold_analysis",
            "update_analysis",
        ]
        for tool in old_tools:
            assert tool not in SPEC_WORKFLOW_CONTENT, f"Should not reference old tool: {tool}"


class TestMcpPrompts:
    def test_generate_spec_no_args(self):
        from mcp_server.server import generate_spec
        res = generate_spec()
        assert "TLGP Screen Specification Workflow" in res
        assert "Step 1" in res
        assert "start fresh" in res

    def test_generate_spec_with_path(self):
        from mcp_server.server import generate_spec
        res = generate_spec(path="my_screenshot.png")
        assert "my_screenshot.png" in res



class TestExampleAnalysisValidation:
    def test_example_analysis_passes_validation(self, tmp_path):
        from tlgp_contracts import DocGenResult

        # Read the raw JSON
        raw_json = get_example_spec_json()
        data_dict = json.loads(raw_json)

        # Convert relative image paths to absolute and touch them
        for node in data_dict.get("nodes", []):
            if "rawImage" in node and node["rawImage"] and node["rawImage"] != "dummy.png":
                node["rawImage"] = str(tmp_path / node["rawImage"])
            if "annotatedImages" in node:
                node["annotatedImages"] = [str(tmp_path / img) for img in node["annotatedImages"]]

        (tmp_path / "dummy_screen.png").touch()
        (tmp_path / "dummy_header.png").touch()
        (tmp_path / "dummy_back_button.png").touch()

        # Write the JSON payload to a temp file so the doc_generator CLI can read it
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(data_dict, indent=2, ensure_ascii=False), encoding="utf-8")

        # Invoke the doc_generator validator CLI via subprocess
        cmd = [sys.executable, "-m", "doc_generator", str(spec_path), "--validate-only", "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"Validator CLI exited with code {proc.returncode}. Stderr: {proc.stderr}"

        result = DocGenResult.model_validate_json(proc.stdout)

        # Assert validation is successful with zero errors and warnings
        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0, f"Unexpected warnings: {result.warnings}"
