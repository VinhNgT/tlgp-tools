from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from mcp_server.manager import DaemonManager


@pytest.mark.anyio
async def test_launch_annotator_timeout_failure(monkeypatch, mock_httpx_client_class):
    # Mock asyncio.create_subprocess_exec
    mock_proc = AsyncMock()
    mock_proc.pid = 9999
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline.return_value = b""
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.readline.return_value = b""

    mock_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(
        "mcp_server.manager.asyncio.create_subprocess_exec",
        mock_exec,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    # Mock AsyncClient so get always fails
    async def mock_get(self, url, *args, **kwargs):
        raise httpx.RequestError("Annotator not ready")

    mock_httpx_client_class.get = mock_get

    manager = DaemonManager()
    result = await manager.launch_annotator()
    assert result["annotator_ready"] is False
    assert result["annotator_url"] == "http://127.0.0.1:8000"


@pytest.mark.anyio
async def test_launch_annotator_import_screenshot(
    tmp_path, monkeypatch, mock_httpx_client_class
):
    mock_proc = AsyncMock()
    mock_proc.pid = 1111
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline.return_value = b""
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.readline.return_value = b""

    mock_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(
        "mcp_server.manager.asyncio.create_subprocess_exec",
        mock_exec,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    dummy_screenshot = tmp_path / "screenshot.png"
    dummy_screenshot.write_bytes(b"image_bytes")

    manager = DaemonManager()
    result = await manager.launch_annotator(path=str(dummy_screenshot))
    assert result["annotator_ready"] is True
    assert result["annotator_url"] == "http://127.0.0.1:8000"

    # Verify create_subprocess_exec args contains the screenshot path
    args = mock_exec.call_args[0]
    assert str(dummy_screenshot.resolve()) in args


@pytest.mark.anyio
async def test_launch_annotator_import_workspace_zip(
    tmp_path, monkeypatch, mock_httpx_client_class
):
    mock_proc = AsyncMock()
    mock_proc.pid = 2222
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline.return_value = b""
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.readline.return_value = b""

    mock_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(
        "mcp_server.manager.asyncio.create_subprocess_exec",
        mock_exec,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    dummy_zip = tmp_path / "workspace.zip"
    dummy_zip.write_bytes(b"zip_bytes")

    manager = DaemonManager()
    result = await manager.launch_annotator(path=str(dummy_zip))
    assert result["annotator_ready"] is True
    assert result["annotator_url"] == "http://127.0.0.1:8000"

    # Verify create_subprocess_exec args contains the workspace zip path
    args = mock_exec.call_args[0]
    assert str(dummy_zip.resolve()) in args


@pytest.mark.anyio
async def test_launch_annotator_resolves_dynamic_port(
    monkeypatch, mock_httpx_client_class
):
    mock_proc = AsyncMock()
    mock_proc.pid = 3333
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline.side_effect = [b"PORT=9191\n", b""]
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.readline.return_value = b""

    mock_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(
        "mcp_server.manager.asyncio.create_subprocess_exec",
        mock_exec,
    )
    monkeypatch.setattr(
        "mcp_server.manager.shutil.which",
        lambda name: "/usr/bin/uv",
    )

    async def mock_get(self, url, *args, **kwargs):
        assert "9191" in url
        mock_res = MagicMock()
        mock_res.status_code = 200
        return mock_res

    mock_httpx_client_class.get = mock_get

    manager = DaemonManager()
    result = await manager.launch_annotator()
    assert result["annotator_ready"] is True
    assert result["annotator_url"] == "http://127.0.0.1:9191"
    assert manager.annotator_url == "http://127.0.0.1:9191"
