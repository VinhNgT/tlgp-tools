"""Tests for MCP prompts."""

from __future__ import annotations

import pytest
from mcp_server.prompts import get_spec_workflow, get_strict_guidelines

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
        assert "{strict_guidelines}" not in SPEC_WORKFLOW_CONTENT
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

    def test_validate_only_documented(self):
        assert "validate_only" in SPEC_WORKFLOW_CONTENT

    def test_export_images_documented(self):
        assert "export_images" in SPEC_WORKFLOW_CONTENT
        # Updated to match the new annotated/ and raw/ subdirectory terminology
        assert "raw/" in SPEC_WORKFLOW_CONTENT
        assert "annotated/" in SPEC_WORKFLOW_CONTENT

    def test_guidelines_not_duplicated_in_workflow(self):
        """Guidelines are delivered via MCP server instructions, not duplicated here."""
        assert "Vietnamese Translation Rule" not in SPEC_WORKFLOW_CONTENT
        assert "Strict Read-Only Mode" not in SPEC_WORKFLOW_CONTENT
        assert "DFS Document Ordering" not in SPEC_WORKFLOW_CONTENT

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_CONTENT
        assert "insertTable" not in SPEC_WORKFLOW_CONTENT

    def test_no_stale_download_parameters(self):
        """Verify old show_root_children/show_component_children params are gone."""
        assert "show_root_children" not in SPEC_WORKFLOW_CONTENT
        assert "show_component_children" not in SPEC_WORKFLOW_CONTENT

    def test_vision_derived_naming_referenced(self):
        """Step 4 references Guideline 12 for vision-derived naming."""
        assert "Guideline 12" in SPEC_WORKFLOW_CONTENT
        assert "bounding box" in SPEC_WORKFLOW_CONTENT.lower()

    def test_explicit_mapping_instructions(self):
        """Workflow must explain UUID-to-integer mapping and mapping.json for cheap agents."""
        assert "mapping.json" in SPEC_WORKFLOW_CONTENT
        assert "sequential integer" in SPEC_WORKFLOW_CONTENT.lower()
        assert "imageDir" in SPEC_WORKFLOW_CONTENT
        assert "topLevelChildren" in SPEC_WORKFLOW_CONTENT


class TestStrictGuidelines:
    def test_content_is_nonempty(self):
        content = get_strict_guidelines()
        assert isinstance(content, str)
        assert len(content) > 100
        assert "Vietnamese Translation Rule" in content
        assert "Strict Read-Only Mode" in content
        assert "DFS Document Ordering" in content
        assert "Annotated vs Raw" in content
        assert "Leaf Components" in content

    def test_no_stale_download_parameters(self):
        content = get_strict_guidelines()
        assert "show_root_children" not in content
        assert "show_component_children" not in content

    def test_vision_derived_naming_guideline(self):
        content = get_strict_guidelines()
        assert "Vision-Derived Naming" in content
        assert "suggestions only" in content.lower()
        assert "bounding box" in content.lower()
