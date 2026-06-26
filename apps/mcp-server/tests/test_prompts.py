"""Tests for MCP prompts."""

from __future__ import annotations

import pytest
from mcp_server.prompts import get_spec_workflow

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
            "finalize",
            "list_exports",
            "parse_annotations",
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
        assert "Step 4" in SPEC_WORKFLOW_CONTENT

    def test_no_more_than_4_steps(self):
        assert "Step 5" not in SPEC_WORKFLOW_CONTENT

    def test_includes_resource_references(self):
        resources = [
            "tlgp://spec/classification-guide",
            "tlgp://spec/example-analysis",
        ]
        for res in resources:
            assert res in SPEC_WORKFLOW_CONTENT, f"Missing resource reference: {res}"

    def test_does_not_reference_deleted_resources(self):
        deleted = [
            "tlgp://spec/schema",
            "tlgp://workspace/state",
        ]
        for res in deleted:
            assert res not in SPEC_WORKFLOW_CONTENT, (
                f"Deleted resource still referenced: {res}"
            )

    def test_vietnamese_language_rule(self):
        assert "Vietnamese" in SPEC_WORKFLOW_CONTENT

    def test_validate_only_documented(self):
        assert "validate_only" in SPEC_WORKFLOW_CONTENT

    def test_export_images_documented(self):
        assert "annotated/" in SPEC_WORKFLOW_CONTENT
        assert "raw/" in SPEC_WORKFLOW_CONTENT

    def test_rules_section_exists(self):
        """Behavioral rules are now inline in the workflow, not a separate file."""
        assert "## Rules" in SPEC_WORKFLOW_CONTENT
        assert "Vietnamese" in SPEC_WORKFLOW_CONTENT
        assert "Vision-Derived Naming" in SPEC_WORKFLOW_CONTENT

    def test_no_external_service_references(self):
        assert "createDocument" not in SPEC_WORKFLOW_CONTENT
        assert "insertTable" not in SPEC_WORKFLOW_CONTENT

    def test_no_stale_download_parameters(self):
        assert "show_root_children" not in SPEC_WORKFLOW_CONTENT
        assert "show_component_children" not in SPEC_WORKFLOW_CONTENT

    def test_prepare_step_documented(self):
        """Step 2 must reference the prepare_analysis tool."""
        assert "prepare_analysis" in SPEC_WORKFLOW_CONTENT
        assert "imageDir" in SPEC_WORKFLOW_CONTENT
        assert "topLevelChildren" in SPEC_WORKFLOW_CONTENT


class TestExampleAnalysisValidation:
    def test_example_analysis_passes_validation(self, tmp_path):
        import json
        from mcp_server.prompts import _read
        from doc_generator.models import AnalysisData
        from doc_generator.validation import validate_analysis

        # Read the raw JSON
        raw_json = _read("example_analysis.json")
        data_dict = json.loads(raw_json)

        # Override imageDir and create files
        data_dict["imageDir"] = str(tmp_path)
        
        annotated_dir = tmp_path / "annotated"
        annotated_dir.mkdir()
        (annotated_dir / "root_screenshot.png").touch()
        (annotated_dir / "1_Thanh_tiêu_đề_a1b2c3d4.png").touch()
        (annotated_dir / "3_Khối_chọn_thuộc_tính_c5d6e7f8.png").touch()

        analysis_data = AnalysisData(**data_dict)
        result = validate_analysis(analysis_data)

        # Assert validation is successful with zero errors, expecting only discrepancy warnings
        assert result.valid is True
        assert len(result.errors) == 0
        other_warnings = [w for w in result.warnings if "Discrepancy at" not in w]
        assert len(other_warnings) == 0, f"Unexpected warnings found: {other_warnings}"

