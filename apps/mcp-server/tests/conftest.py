"""Shared fixtures for MCP server tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.services import SpecGeneratorService


@pytest.fixture
def mock_httpx_client_class(monkeypatch):
    """Fixture that mocks httpx.AsyncClient with a configurable class.
    Tests can use this, or override it if they need custom behavior.
    """
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

        async def post(self, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

        async def request(self, method, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    return MockAsyncClient


@pytest.fixture
def mcp_ctx():
    """Create a mock MCP Context that provides lifespan_context."""
    def _make_ctx(
        client: WorkspaceClient | None = None,
        daemon_manager: DaemonManager | None = None,
        spec_service: SpecGeneratorService | None = None,
    ) -> MagicMock:
        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.log = AsyncMock()
        ctx.request_context.lifespan_context = {
            "client": client or MagicMock(spec=WorkspaceClient),
            "daemon_manager": daemon_manager or MagicMock(spec=DaemonManager),
            "spec_service": spec_service or MagicMock(spec=SpecGeneratorService),
        }
        return ctx
    return _make_ctx
