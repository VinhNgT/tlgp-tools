"""Tests for MCP prompts."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from mcp_server.prompts import SPEC_WORKFLOW_PROMPT
from mcp_server.server import spec_doc_workflow


class TestSpecWorkflowPrompt:
    def test_is_nonempty(self):
        assert isinstance(SPEC_WORKFLOW_PROMPT, str)
        assert len(SPEC_WORKFLOW_PROMPT) > 100

    def test_references_current_tools(self):
        tools = [
            "launch_annotator",
            "get_workspace_state",
            "download_image",
            "download_workspace_assets",
            "generate_spec_doc",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_PROMPT, f"Missing tool reference: {tool}"

    def test_does_not_reference_old_tools(self):
        old_tools = [
            "prepare_analysis",
            "update_analysis",
            "finalize",
            "list_exports",
            "parse_annotations",
            "scaffold_analysis",
            "validate_analysis",
            "generate_docx",
        ]
        for tool in old_tools:
            assert tool not in SPEC_WORKFLOW_PROMPT, (
                f"Old tool still referenced: {tool}"
            )

    def test_section_prefix_placeholder(self):
        assert "{section_prefix}" in SPEC_WORKFLOW_PROMPT

    def test_format_with_prefix(self):
        formatted = SPEC_WORKFLOW_PROMPT.replace("{section_prefix}", "2.1")
        assert "2.1" in formatted
        assert "{section_prefix}" not in formatted

    def test_has_all_steps(self):
        """Verify the prompt covers the 3-step workflow."""
        assert "Step 1" in SPEC_WORKFLOW_PROMPT
        assert "Step 2" in SPEC_WORKFLOW_PROMPT
        assert "Step 3" in SPEC_WORKFLOW_PROMPT

    def test_no_more_than_3_steps(self):
        assert "Step 4" not in SPEC_WORKFLOW_PROMPT

    def test_includes_schema_reference(self):
        assert "sectionPrefix" in SPEC_WORKFLOW_PROMPT
        assert "exportDir" in SPEC_WORKFLOW_PROMPT
        assert "controlType" in SPEC_WORKFLOW_PROMPT

    def test_includes_control_types_guide(self):
        assert "Button" in SPEC_WORKFLOW_PROMPT
        assert "TextField" in SPEC_WORKFLOW_PROMPT
        assert "Classification Rules" in SPEC_WORKFLOW_PROMPT

    def test_includes_annotation_format(self):
        assert "raw.png" in SPEC_WORKFLOW_PROMPT
        assert "exportDir" in SPEC_WORKFLOW_PROMPT
        assert "sectionPrefix" in SPEC_WORKFLOW_PROMPT

    def test_includes_example(self):
        assert "Chi tiết sản phẩm" in SPEC_WORKFLOW_PROMPT
        assert "Thanh tiêu đề" in SPEC_WORKFLOW_PROMPT

    def test_source_priority_documented(self):
        assert "Source Priority" in SPEC_WORKFLOW_PROMPT
        assert "Screenshots" in SPEC_WORKFLOW_PROMPT
        assert "Source code" in SPEC_WORKFLOW_PROMPT

    def test_vietnamese_language_rule(self):
        assert "Vietnamese" in SPEC_WORKFLOW_PROMPT
        assert "must be in Vietnamese" in SPEC_WORKFLOW_PROMPT

    def test_validate_only_documented(self):
        assert "validate_only" in SPEC_WORKFLOW_PROMPT

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_PROMPT
        assert "insertTable" not in SPEC_WORKFLOW_PROMPT

    @pytest.mark.anyio
    @patch("mcp_server.server.client.get_workspace_state", new_callable=AsyncMock)
    async def test_spec_doc_workflow_renders(self, mock_get_state):
        mock_get_state.return_value = {"components": {}, "screen": {}}
        res = await spec_doc_workflow("3.2")
        assert isinstance(res, list)
        assert len(res) == 2
        assert "3.2" in res[0]
        assert res[1]["role"] == "user"
        assert res[1]["content"]["type"] == "resource"
        assert res[1]["content"]["resource"]["uri"] == "tlgp://workspace/state"
        mock_get_state.assert_called_once()
