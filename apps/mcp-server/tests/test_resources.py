"""Tests for MCP resources."""

from __future__ import annotations

from mcp_server.server import (
    get_spec_classification_guide_resource,
    get_spec_example_analysis_resource,
)


class TestMcpResources:
    def test_get_spec_classification_guide_resource(self):
        result = get_spec_classification_guide_resource()
        assert "Classification Guide" in result
        assert "Button" in result

    def test_get_spec_example_analysis_resource(self):
        result = get_spec_example_analysis_resource()
        assert "Example" in result
        assert "chi tiết sản phẩm" in result.lower()
