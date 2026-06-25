"""Tests for MCP resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from mcp_server.server import (
    get_spec_classification_guide_resource,
    get_spec_example_analysis_resource,
    get_spec_schema_resource,
    get_workspace_state_resource,
)
from tlgp_contracts import WorkspaceState


class TestMcpResources:
    @pytest.mark.anyio
    @patch("mcp_server.server.get_client")
    async def test_get_workspace_state_resource(self, mock_get_client):
        mock_state = WorkspaceState(workspaceId=uuid4())
        mock_client = MagicMock()
        mock_client.get_workspace_state = AsyncMock(return_value=mock_state)
        mock_get_client.return_value = mock_client

        result = await get_workspace_state_resource()
        assert "components" in result
        assert "screen" in result
        mock_client.get_workspace_state.assert_called_once()

    def test_get_spec_schema_resource(self):
        result = get_spec_schema_resource()
        assert "Schema Reference" in result
        assert "imageDir" in result

    def test_get_spec_classification_guide_resource(self):
        result = get_spec_classification_guide_resource()
        assert "Classification Guide" in result
        assert "Button" in result

    def test_get_spec_example_analysis_resource(self):
        result = get_spec_example_analysis_resource()
        assert "Example" in result
        assert "Chi tiết sản phẩm" in result
