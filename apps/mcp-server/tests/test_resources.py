"""Tests for MCP resources."""

from __future__ import annotations

from mcp_server.server import (
    get_spec_example_analysis_resource,
    get_spec_validation_guide_resource,
    get_spec_writing_guide_resource,
)


class TestMcpResources:
    def test_get_spec_validation_guide_resource(self):
        result = get_spec_validation_guide_resource()
        assert "Validation" in result
        assert "Complexity" in result
        assert "Placeholder" in result

    def test_get_spec_writing_guide_resource(self):
        result = get_spec_writing_guide_resource()
        assert "Writing" in result
        assert "Classification" in result
        assert "Button" in result

    def test_get_spec_example_analysis_resource(self):
        result = get_spec_example_analysis_resource()
        assert "Example" in result
        assert "chi tiết sản phẩm" in result.lower()
