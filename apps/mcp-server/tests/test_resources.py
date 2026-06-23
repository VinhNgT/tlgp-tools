"""Tests for MCP resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_server.server import (
    get_component_image_resource,
    get_daemon_logs_resource,
    get_daemon_status_resource,
    get_spec_classification_guide_resource,
    get_spec_example_analysis_resource,
    get_spec_schema_resource,
    get_workspace_state_resource,
)


class TestMcpResources:
    @pytest.mark.anyio
    @patch("mcp_server.server.get_client")
    async def test_get_workspace_state_resource(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_workspace_state = AsyncMock(return_value={"components": {}, "screen": {}})
        mock_get_client.return_value = mock_client

        result = await get_workspace_state_resource()
        assert "components" in result
        assert "screen" in result
        mock_client.get_workspace_state.assert_called_once()

    @pytest.mark.anyio
    @patch("mcp_server.server.get_client")
    async def test_get_component_image_resource(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_image_bytes = AsyncMock(return_value=b"image_bytes")
        mock_get_client.return_value = mock_client

        result = await get_component_image_resource("comp_123")
        assert result == b"image_bytes"
        mock_client.get_image_bytes.assert_called_once_with("comp_123")

    @patch("mcp_server.server.get_daemon_manager")
    def test_get_daemon_logs_resource(self, mock_get_daemon_manager):
        mock_manager = MagicMock()
        mock_manager.read_daemon_logs.return_value = {"logs": "log line 1\nlog line 2\n"}
        mock_get_daemon_manager.return_value = mock_manager

        result = get_daemon_logs_resource("annotator")
        assert "log line 1" in result
        mock_manager.read_daemon_logs.assert_called_once_with("annotator", lines=100)

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

    @pytest.mark.anyio
    @patch("mcp_server.server.get_daemon_manager")
    async def test_get_daemon_status_resource(self, mock_get_daemon_manager):
        mock_manager = MagicMock()
        mock_manager.get_status = AsyncMock(
            return_value={"annotator": {"running": True}}
        )
        mock_get_daemon_manager.return_value = mock_manager

        result = await get_daemon_status_resource()
        assert "annotator" in result
        assert "running" in result
        mock_manager.get_status.assert_called_once()

