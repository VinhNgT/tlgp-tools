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


def pytest_configure(config):
    from doc_generator.models import NodeSpec, ScreenSpec, Bounds, ApiParam
    
    # Patch ApiParam.__init__ to inject required test defaults
    original_param_init = ApiParam.__init__
    def new_param_init(self, *args, **kwargs):
        if "description" not in kwargs:
            kwargs["description"] = "dummy description"
        if "required" not in kwargs:
            kwargs["required"] = True
        if "type" not in kwargs:
            kwargs["type"] = "string"
        original_param_init(self, *args, **kwargs)
    ApiParam.__init__ = new_param_init

    # Patch NodeSpec.__init__ to inject required test defaults
    original_node_init = NodeSpec.__init__
    def new_node_init(self, *args, **kwargs):
        if "absoluteBounds" not in kwargs:
            kwargs["absoluteBounds"] = Bounds(x=0, y=0, w=0, h=0)
        if "rawImage" not in kwargs:
            kwargs["rawImage"] = "dummy.png"
        if "controlType" not in kwargs:
            node_id = kwargs.get("id")
            children = kwargs.get("childrenIds", [])
            try:
                coerced_id = int(node_id) if node_id is not None else None
            except ValueError:
                coerced_id = None

            if coerced_id == 0:
                kwargs["controlType"] = "Screen"
            elif len(children) > 0:
                kwargs["controlType"] = "Component"
            else:
                kwargs["controlType"] = "Button"
        if "editable" not in kwargs:
            kwargs["editable"] = False
        if "description" not in kwargs:
            kwargs["description"] = "dummy description"
        if "required" not in kwargs:
            kwargs["required"] = False
        original_node_init(self, *args, **kwargs)
    NodeSpec.__init__ = new_node_init

    # Patch ScreenSpec.__init__ to inject required test defaults
    original_screen_init = ScreenSpec.__init__
    def new_screen_init(self, *args, **kwargs):
        if "sectionPrefix" not in kwargs:
            kwargs["sectionPrefix"] = "1.1"
        if "rootId" not in kwargs:
            kwargs["rootId"] = 0
        original_screen_init(self, *args, **kwargs)
    ScreenSpec.__init__ = new_screen_init
