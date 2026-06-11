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
            "list_exports",
            "parse_annotations",
            "scaffold_analysis",
            "validate_analysis",
            "generate_docx",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_PROMPT, f"Missing tool reference: {tool}"

    def test_references_all_resources(self):
        resources = [
            "tlgp://schema/analysis-json",
            "tlgp://schema/control-types",
            "tlgp://spec/formatting",
        ]
        for res in resources:
            assert res in SPEC_WORKFLOW_PROMPT, f"Missing resource reference: {res}"

    def test_section_prefix_placeholder(self):
        assert "{section_prefix}" in SPEC_WORKFLOW_PROMPT

    def test_format_with_prefix(self):
        formatted = SPEC_WORKFLOW_PROMPT.format(section_prefix="2.1")
        assert "2.1" in formatted
        assert "{section_prefix}" not in formatted

    def test_has_all_steps(self):
        """Verify the prompt covers the complete workflow."""
        assert "Step 1" in SPEC_WORKFLOW_PROMPT
        assert "Step 2" in SPEC_WORKFLOW_PROMPT
        assert "Step 3" in SPEC_WORKFLOW_PROMPT
        assert "Step 4" in SPEC_WORKFLOW_PROMPT
        assert "Step 5" in SPEC_WORKFLOW_PROMPT
        assert "Step 6" in SPEC_WORKFLOW_PROMPT
        assert "Step 7" in SPEC_WORKFLOW_PROMPT

    def test_no_external_service_references(self):
        """Prompt must only reference internal tools, not external services."""
        lower = SPEC_WORKFLOW_PROMPT.lower()
        assert "createDocument" not in SPEC_WORKFLOW_PROMPT
        assert "insertTable" not in SPEC_WORKFLOW_PROMPT
