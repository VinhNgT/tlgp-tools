"""Tests for MCP prompts."""

from __future__ import annotations

from tlgp_mcp_server.prompts import SPEC_WORKFLOW_PROMPT


class TestSpecWorkflowPrompt:
    def test_is_nonempty(self):
        assert isinstance(SPEC_WORKFLOW_PROMPT, str)
        assert len(SPEC_WORKFLOW_PROMPT) > 100

    def test_references_all_tools(self):
        tools = [
            "launch_annotator",
            "prepare_analysis",
            "update_analysis",
            "finalize",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_PROMPT, f"Missing tool reference: {tool}"

    def test_does_not_reference_old_tools(self):
        old_tools = [
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
        formatted = SPEC_WORKFLOW_PROMPT.format(section_prefix="2.1")
        assert "2.1" in formatted
        assert "{section_prefix}" not in formatted

    def test_has_all_steps(self):
        """Verify the prompt covers the complete 4-step workflow."""
        assert "Step 1" in SPEC_WORKFLOW_PROMPT
        assert "Step 2" in SPEC_WORKFLOW_PROMPT
        assert "Step 3" in SPEC_WORKFLOW_PROMPT
        assert "Step 4" in SPEC_WORKFLOW_PROMPT

    def test_no_more_than_4_steps(self):
        """The simplified prompt should have exactly 4 steps."""
        assert "Step 5" not in SPEC_WORKFLOW_PROMPT

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_PROMPT
        assert "insertTable" not in SPEC_WORKFLOW_PROMPT

    def test_source_priority_documented(self):
        assert "Source Priority" in SPEC_WORKFLOW_PROMPT
        assert "Screenshots" in SPEC_WORKFLOW_PROMPT
        assert "Source code" in SPEC_WORKFLOW_PROMPT

    def test_update_analysis_json_example(self):
        """Prompt should include JSON path examples for the agent."""
        assert "components[" in SPEC_WORKFLOW_PROMPT
        assert "controlType" in SPEC_WORKFLOW_PROMPT
