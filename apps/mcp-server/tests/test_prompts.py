"""Tests for MCP prompts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_server.prompts import get_spec_workflow_prompt, get_strict_guidelines_content
from mcp_server.server import spec_doc_workflow

SPEC_WORKFLOW_PROMPT = ""


@pytest.fixture(autouse=True, scope="module")
def setup_spec_workflow_prompt():
    global SPEC_WORKFLOW_PROMPT
    SPEC_WORKFLOW_PROMPT = get_spec_workflow_prompt()


class TestSpecWorkflowPrompt:
    def test_is_nonempty(self):
        assert isinstance(SPEC_WORKFLOW_PROMPT, str)
        assert len(SPEC_WORKFLOW_PROMPT) > 100

    def test_references_current_tools(self):
        tools = [
            "launch_annotator",
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
            "get_workspace_state",
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
        """Verify the prompt covers the high-level workflow."""
        assert "Step 1" in SPEC_WORKFLOW_PROMPT
        assert "Step 2" in SPEC_WORKFLOW_PROMPT
        assert "Step 3" in SPEC_WORKFLOW_PROMPT
        assert "Step 4" in SPEC_WORKFLOW_PROMPT

    def test_no_more_than_4_steps(self):
        assert "Step 5" not in SPEC_WORKFLOW_PROMPT

    def test_includes_resource_references(self):
        resources = [
            "tlgp://spec/classification-guide",
            "tlgp://spec/schema",
            "tlgp://spec/example-analysis",
            "tlgp://workspace/state",
        ]
        for res in resources:
            assert res in SPEC_WORKFLOW_PROMPT, f"Missing resource reference: {res}"

    def test_vietnamese_language_rule(self):
        assert "Vietnamese" in SPEC_WORKFLOW_PROMPT
        assert "must be in Vietnamese" in SPEC_WORKFLOW_PROMPT

    def test_validate_only_documented(self):
        assert "validate_only" in SPEC_WORKFLOW_PROMPT

    def test_children_annotations_documented(self):
        assert "show_root_children=True" in SPEC_WORKFLOW_PROMPT
        assert "show_component_children=True" in SPEC_WORKFLOW_PROMPT
        assert "show_root_children=False" in SPEC_WORKFLOW_PROMPT
        assert "show_component_children=False" in SPEC_WORKFLOW_PROMPT
        assert "children annotations" in SPEC_WORKFLOW_PROMPT.lower()

    def test_dfs_ordering_documented(self):
        assert "dfs" in SPEC_WORKFLOW_PROMPT.lower()
        assert "depth-first search" in SPEC_WORKFLOW_PROMPT.lower()

    def test_non_leaf_completeness_documented(self):
        assert "non-leaf box" in SPEC_WORKFLOW_PROMPT.lower()
        assert "isleaf" in SPEC_WORKFLOW_PROMPT.lower()
        assert "false" in SPEC_WORKFLOW_PROMPT.lower()

    def test_leaf_components_analysis_documented(self):
        assert "leaf component" in SPEC_WORKFLOW_PROMPT.lower()
        assert "isleaf" in SPEC_WORKFLOW_PROMPT.lower()
        assert "true" in SPEC_WORKFLOW_PROMPT.lower()

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_PROMPT
        assert "insertTable" not in SPEC_WORKFLOW_PROMPT

    @pytest.mark.anyio
    @patch("mcp_server.server.get_client")
    async def test_spec_doc_workflow_renders(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_workspace_state = AsyncMock(return_value={"components": {}, "screen": {}})
        mock_get_client.return_value = mock_client
        res = await spec_doc_workflow("3.2")
        assert isinstance(res, list)
        assert len(res) == 2
        assert "3.2" in res[0]
        assert res[1]["role"] == "user"
        assert res[1]["content"]["type"] == "resource"
        assert res[1]["content"]["resource"]["uri"] == "tlgp://workspace/state"
        mock_client.get_workspace_state.assert_called_once()


class TestStrictGuidelines:
    def test_get_strict_guidelines_content(self):
        content = get_strict_guidelines_content()
        assert isinstance(content, str)
        assert len(content) > 100
        assert "Vietnamese Translation Rule" in content
        assert "Strict Read-Only Mode" in content
        assert "DFS Document Ordering" in content
        assert "Children Annotations Overlay" in content
        assert "Leaf Components" in content

