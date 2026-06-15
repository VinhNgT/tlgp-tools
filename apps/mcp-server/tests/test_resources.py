"""Tests for MCP resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from mcp_server.server import (
    get_component_image_resource,
    get_daemon_logs_resource,
    get_spec_classification_guide_resource,
    get_spec_example_analysis_resource,
    get_spec_schema_resource,
    get_workspace_state_resource,
)


class TestMcpResources:
    @pytest.mark.anyio
    @patch("mcp_server.server.get_workspace_state_impl", new_callable=AsyncMock)
    async def test_get_workspace_state_resource(self, mock_state_impl):
        mock_state = {"components": {}, "screen": {}}
        mock_state_impl.return_value = mock_state

        result = await get_workspace_state_resource()
        assert "components" in result
        assert "screen" in result
        mock_state_impl.assert_called_once()

    @pytest.mark.anyio
    @patch("mcp_server.server.get_image_bytes_impl", new_callable=AsyncMock)
    async def test_get_component_image_resource(self, mock_image_impl):
        mock_image_impl.return_value = b"image_bytes"

        result = await get_component_image_resource("comp_123")
        assert result == b"image_bytes"
        mock_image_impl.assert_called_once_with("comp_123")

    @patch("mcp_server.server.read_daemon_logs_impl")
    def test_get_daemon_logs_resource(self, mock_logs_impl):
        mock_logs_impl.return_value = {"logs": "log line 1\nlog line 2\n"}

        result = get_daemon_logs_resource("engine")
        assert "log line 1" in result
        mock_logs_impl.assert_called_once_with("engine", lines=100)

    def test_get_spec_schema_resource(self):
        result = get_spec_schema_resource()
        assert "Schema Reference" in result
        assert "exportDir" in result

    def test_get_spec_classification_guide_resource(self):
        result = get_spec_classification_guide_resource()
        assert "Classification Guide" in result
        assert "Button" in result

    def test_get_spec_example_analysis_resource(self):
        result = get_spec_example_analysis_resource()
        assert "Example" in result
        assert "Chi tiết sản phẩm" in result

