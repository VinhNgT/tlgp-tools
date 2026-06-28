"""Tests for MCP prompts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from doc_generator.models import ScreenSpec
from doc_generator.validation import validate_spec
from mcp_server.prompts import _read, get_spec_workflow
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
            "prepare_analysis",
            "generate_spec_doc",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_CONTENT, f"Missing tool reference: {tool}"

    def test_does_not_reference_old_tools(self):
        old_tools = [
            "export_workspace",
            "export_images",
            "scaffold_analysis",
            "update_analysis",
        ]
        for tool in old_tools:
            assert tool not in SPEC_WORKFLOW_CONTENT, f"Should not reference old tool: {tool}"


class TestExampleAnalysisValidation:
    def test_example_analysis_passes_validation(self, tmp_path):
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

        spec = ScreenSpec(**data_dict)
        result = validate_spec(spec)

        # Assert validation is successful with zero errors and warnings
        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0, f"Unexpected warnings: {result.warnings}"
