from __future__ import annotations

import io
from unittest.mock import MagicMock

import httpx
import pytest
from mcp_server.manager import DaemonManager


@pytest.mark.anyio
async def test_launch_annotator_timeout_failure(monkeypatch):
    # Mock subprocess.Popen
    mock_popen = MagicMock()
    mock_popen.return_value.pid = 9999
    monkeypatch.setattr(
        "mcp_server.manager.subprocess.Popen",
        mock_popen,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    # Mock AsyncClient so get always fails
    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            raise httpx.RequestError("Annotator not ready")

    monkeypatch.setattr(
        "mcp_server.manager.httpx.AsyncClient",
        MockAsyncClient,
    )

    manager = DaemonManager()
    result = await manager.launch_annotator()
    assert result["annotator_pid"] == 9999
    assert result["annotator_ready"] is False


@pytest.mark.anyio
async def test_launch_annotator_import_screenshot(tmp_path, monkeypatch):
    mock_popen = MagicMock()
    mock_popen.return_value.pid = 1111
    monkeypatch.setattr(
        "mcp_server.manager.subprocess.Popen",
        mock_popen,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    # Mock AsyncClient to succeed on get
    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

    monkeypatch.setattr(
        "mcp_server.manager.httpx.AsyncClient",
        MockAsyncClient,
    )

    dummy_screenshot = tmp_path / "screenshot.png"
    dummy_screenshot.write_bytes(b"image_bytes")

    manager = DaemonManager()
    result = await manager.launch_annotator(screenshot_path=str(dummy_screenshot))
    assert result["annotator_pid"] == 1111
    assert result["annotator_ready"] is True

    # Verify Popen args contains the screenshot path
    args = mock_popen.call_args[0][0]
    assert str(dummy_screenshot.resolve()) in args


@pytest.mark.anyio
async def test_launch_annotator_import_workspace_zip(tmp_path, monkeypatch):
    mock_popen = MagicMock()
    mock_popen.return_value.pid = 2222
    monkeypatch.setattr(
        "mcp_server.manager.subprocess.Popen",
        mock_popen,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    # Mock AsyncClient to succeed on get
    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

    monkeypatch.setattr(
        "mcp_server.manager.httpx.AsyncClient",
        MockAsyncClient,
    )

    dummy_zip = tmp_path / "workspace.zip"
    dummy_zip.write_bytes(b"zip_bytes")

    manager = DaemonManager()
    result = await manager.launch_annotator(workspace_zip=str(dummy_zip))
    assert result["annotator_pid"] == 2222
    assert result["annotator_ready"] is True

    # Verify Popen args contains the workspace zip path
    args = mock_popen.call_args[0][0]
    assert str(dummy_zip.resolve()) in args


@pytest.mark.anyio
async def test_launch_annotator_resolves_dynamic_port(monkeypatch):
    mock_popen = MagicMock()
    mock_popen.return_value.pid = 3333

    mock_popen.return_value.stdout = io.BytesIO(b"PORT=9191\n")
    mock_popen.return_value.stderr = io.BytesIO(b"")

    monkeypatch.setattr(
        "mcp_server.manager.subprocess.Popen",
        mock_popen,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            assert "9191" in url
            mock_res = MagicMock()
            mock_res.status_code = 200
            return mock_res

    monkeypatch.setattr(
        "mcp_server.manager.httpx.AsyncClient",
        MockAsyncClient,
    )

    manager = DaemonManager()
    result = await manager.launch_annotator()
    assert result["annotator_pid"] == 3333
    assert result["annotator_ready"] is True
    assert result["port"] == 9191
    assert manager.annotator_url == "http://127.0.0.1:9191"
