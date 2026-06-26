"""Tests for MCP resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.server import (
    _lifespan_state,
    get_spec_classification_guide_resource,
    get_spec_example_analysis_resource,
    get_workspace_state_resource,
)
from tlgp_contracts import WorkspaceState


class TestMcpResources:
    @pytest.mark.anyio
    async def test_get_workspace_state_resource(self):
        mock_state = WorkspaceState(workspaceId=uuid4())
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.get_workspace_state = AsyncMock(return_value=mock_state)

        _lifespan_state.client = mock_client
        try:
            result = await get_workspace_state_resource()
            assert "components" in result
            assert "screen" in result
            mock_client.get_workspace_state.assert_called_once()
        finally:
            _lifespan_state.client = None

    def test_get_spec_classification_guide_resource(self):
        result = get_spec_classification_guide_resource()
        assert "Classification Guide" in result
        assert "Button" in result

    def test_get_spec_example_analysis_resource(self):
        result = get_spec_example_analysis_resource()
        assert "Example" in result
        assert "Chi tiết sản phẩm" in result
