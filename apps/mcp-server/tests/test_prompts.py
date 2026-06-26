"""Tests for MCP prompts."""

from __future__ import annotations

import pytest
from mcp_server.prompts import get_spec_workflow_content, get_strict_guidelines_content

SPEC_WORKFLOW_CONTENT = ""


@pytest.fixture(autouse=True, scope="module")
def setup_spec_workflow_content():
    global SPEC_WORKFLOW_CONTENT
    SPEC_WORKFLOW_CONTENT = get_spec_workflow_content()


class TestSpecWorkflowContent:
    def test_is_nonempty(self):
        assert isinstance(SPEC_WORKFLOW_CONTENT, str)
        assert len(SPEC_WORKFLOW_CONTENT) > 100

    def test_references_current_tools(self):
        tools = [
            "launch_annotator",
            "export_images",
            "generate_spec_doc",
        ]
        for tool in tools:
            assert tool in SPEC_WORKFLOW_CONTENT, f"Missing tool reference: {tool}"

    def test_does_not_reference_old_tools(self):
        old_tools = [
            "export_workspace",
            "prepare_analysis",
            "update_analysis",
            "finalize",
            "list_exports",
            "parse_annotations",
            "scaffold_analysis",
            "validate_analysis",
            "generate_docx",
            "get_workspace_state",
            "download_workspace_assets",
        ]
        for tool in old_tools:
            assert tool not in SPEC_WORKFLOW_CONTENT, (
                f"Old tool still referenced: {tool}"
            )

    def test_no_unsubstituted_template_variables(self):
        # All template variables should be resolved
        assert "{section_prefix}" not in SPEC_WORKFLOW_CONTENT
        assert "{annotation_json_example}" not in SPEC_WORKFLOW_CONTENT

    def test_has_all_steps(self):
        """Verify the prompt covers the high-level workflow."""
        assert "Step 1" in SPEC_WORKFLOW_CONTENT
        assert "Step 2" in SPEC_WORKFLOW_CONTENT
        assert "Step 3" in SPEC_WORKFLOW_CONTENT
        assert "Step 4" in SPEC_WORKFLOW_CONTENT
        assert "Step 5" in SPEC_WORKFLOW_CONTENT

    def test_no_more_than_5_steps(self):
        assert "Step 6" not in SPEC_WORKFLOW_CONTENT

    def test_includes_resource_references(self):
        resources = [
            "tlgp://spec/classification-guide",
            "tlgp://spec/schema",
            "tlgp://spec/example-analysis",
            "tlgp://workspace/state",
        ]
        for res in resources:
            assert res in SPEC_WORKFLOW_CONTENT, f"Missing resource reference: {res}"

    def test_vietnamese_language_rule(self):
        assert "Vietnamese" in SPEC_WORKFLOW_CONTENT
        assert "must be in Vietnamese" in SPEC_WORKFLOW_CONTENT

    def test_validate_only_documented(self):
        assert "validate_only" in SPEC_WORKFLOW_CONTENT

    def test_export_images_documented(self):
        assert "export_images" in SPEC_WORKFLOW_CONTENT
        # Updated to match the new annotated/ and raw/ subdirectory terminology
        assert "raw/" in SPEC_WORKFLOW_CONTENT
        assert "annotated/" in SPEC_WORKFLOW_CONTENT

    def test_dfs_ordering_documented(self):
        assert "dfs" in SPEC_WORKFLOW_CONTENT.lower()
        assert "depth-first search" in SPEC_WORKFLOW_CONTENT.lower()

    def test_non_leaf_completeness_documented(self):
        assert "non-leaf box" in SPEC_WORKFLOW_CONTENT.lower()
        assert "isleaf" in SPEC_WORKFLOW_CONTENT.lower()
        assert "false" in SPEC_WORKFLOW_CONTENT.lower()

    def test_leaf_components_analysis_documented(self):
        assert "leaf component" in SPEC_WORKFLOW_CONTENT.lower()
        assert "isleaf" in SPEC_WORKFLOW_CONTENT.lower()
        assert "true" in SPEC_WORKFLOW_CONTENT.lower()

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_CONTENT
        assert "insertTable" not in SPEC_WORKFLOW_CONTENT

    def test_no_stale_download_parameters(self):
        """Verify old show_root_children/show_component_children params are gone."""
        assert "show_root_children" not in SPEC_WORKFLOW_CONTENT
        assert "show_component_children" not in SPEC_WORKFLOW_CONTENT


class TestStrictGuidelines:
    def test_get_strict_guidelines_content(self):
        content = get_strict_guidelines_content()
        assert isinstance(content, str)
        assert len(content) > 100
        assert "Vietnamese Translation Rule" in content
        assert "Strict Read-Only Mode" in content
        assert "DFS Document Ordering" in content
        assert "Annotated vs Raw" in content
        assert "Leaf Components" in content

    def test_no_stale_download_parameters(self):
        content = get_strict_guidelines_content()
        assert "show_root_children" not in content
        assert "show_component_children" not in content
