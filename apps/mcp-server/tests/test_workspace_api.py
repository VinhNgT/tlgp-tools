"""Tests for the WorkspaceClient API methods."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.exceptions import ApiClientError
from tlgp_contracts import WorkspaceState


def test_api_client_error_serialization():
    err = ApiClientError(
        message="Failed operation",
        status_code=400,
        url="http://localhost/api",
        method="GET",
        backend_detail="Invalid query parameters",
    )

    assert (
        "ApiClientError: Failed operation [Status: 400] (GET http://localhost/api)"
        in str(err)
    )
    assert "Backend Detail" in str(err)

    serialized = err.to_dict()
    assert serialized["error"] == "ApiClientError"
    assert serialized["message"] == "Failed operation"
    assert serialized["status_code"] == 400
    assert serialized["url"] == "http://localhost/api"
    assert serialized["method"] == "GET"
    assert serialized["backend_detail"] == "Invalid query parameters"


class TestWorkspaceApi:
    @pytest.mark.anyio
    async def test_get_workspace_state_success(self, monkeypatch, mock_httpx_client_class):
        workspace_id = str(uuid4())

        async def mock_request(self, method, url, *args, **kwargs):
            assert method == "GET"
            assert "workspace/state" in url
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {"version": 1, "workspaceId": workspace_id}
            return mock_res

        mock_httpx_client_class.request = mock_request

        client = WorkspaceClient()
        res = await client.get_workspace_state()
        assert isinstance(res, WorkspaceState)
        assert res.version == 1
        assert str(res.workspaceId) == workspace_id

    @pytest.mark.anyio
    async def test_check_connection_success(self, monkeypatch, mock_httpx_client_class):
        async def mock_request(self, method, url, *args, **kwargs):
            assert method == "GET"
            assert "health" in url
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {"status": "ok"}
            return mock_res

        mock_httpx_client_class.request = mock_request

        client = WorkspaceClient()
        assert await client.check_connection() is True

    @pytest.mark.anyio
    async def test_check_connection_failure(self, monkeypatch, mock_httpx_client_class):
        async def mock_request(self, method, url, *args, **kwargs):
            raise httpx.RequestError("Connection refused")

        mock_httpx_client_class.request = mock_request

        client = WorkspaceClient()
        assert await client.check_connection() is False

    @pytest.mark.anyio
    async def test_get_workspace_state_http_status_error(self, monkeypatch, mock_httpx_client_class):
        req = httpx.Request("GET", "http://localhost/state")
        resp = httpx.Response(404, request=req, text="Not found details")

        async def mock_request(self, method, url, *args, **kwargs):
            raise httpx.HTTPStatusError("Not Found", request=req, response=resp)

        mock_httpx_client_class.request = mock_request

        client = WorkspaceClient()
        with pytest.raises(ApiClientError) as exc_info:
            await client.get_workspace_state()

        err = exc_info.value
        assert err.status_code == 404
        assert err.url is not None
        assert "localhost/state" in err.url
        assert err.method == "GET"
        assert err.backend_detail == "Not found details"

    @pytest.mark.anyio
    async def test_get_workspace_state_request_error(self, monkeypatch, mock_httpx_client_class):
        req = httpx.Request("GET", "http://localhost/state")

        async def mock_request(self, method, url, *args, **kwargs):
            raise httpx.RequestError("Connection refused", request=req)

        mock_httpx_client_class.request = mock_request

        client = WorkspaceClient()
        with pytest.raises(ApiClientError) as exc_info:
            await client.get_workspace_state()

        err = exc_info.value
        assert "Connection refused" in err.message
        assert err.status_code is None
        assert err.url is not None
        assert "localhost/state" in err.url




    @pytest.mark.anyio
    async def test_export_workspace_zip_success(self, tmp_path, monkeypatch, mock_httpx_client_class):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("workspace.json", '{"workspaceId": "abc"}')
            zf.writestr("screenshot.png", b"image_bytes")

        async def mock_request(self, method, url, *args, **kwargs):
            assert method == "GET"
            assert "workspace/export" in url
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.content = zip_buf.getvalue()
            return mock_res

        mock_httpx_client_class.request = mock_request

        out_zip = tmp_path / "workspace.zip"
        client = WorkspaceClient()
        await client.export_workspace(str(out_zip))

        assert out_zip.exists()
        with zipfile.ZipFile(out_zip, "r") as zf:
            assert "workspace.json" in zf.namelist()
            assert "screenshot.png" in zf.namelist()


    @pytest.mark.anyio
    async def test_export_images_extracted_success(self, tmp_path, monkeypatch, mock_httpx_client_class):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("mapping.json", '{"components": {}}')
            zf.writestr("comp1.png", b"comp_bytes")

        async def mock_request(self, method, url, *args, **kwargs):
            assert method == "GET"
            assert "workspace/export-images" in url
            assert kwargs.get("params", {}).get("mode") == "both"
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.content = zip_buf.getvalue()
            return mock_res

        mock_httpx_client_class.request = mock_request

        out_dir = tmp_path / "crops_extracted"
        client = WorkspaceClient()
        res = await client.export_images(str(out_dir))

        assert res["output_path"] == str(out_dir.resolve())
        assert (out_dir / "mapping.json").exists()
        assert (out_dir / "comp1.png").exists()

    @pytest.mark.anyio
    async def test_export_images_invalid_mapping_json(self, tmp_path, mock_httpx_client_class):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("mapping.json", 'invalid_json{')
            zf.writestr("comp1.png", b"comp_bytes")

        async def mock_request(self, method, url, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.content = zip_buf.getvalue()
            return mock_res

        mock_httpx_client_class.request = mock_request

        out_dir = tmp_path / "crops_invalid"
        client = WorkspaceClient()
        res = await client.export_images(str(out_dir))

        assert res["output_path"] == str(out_dir.resolve())
        assert (out_dir / "mapping.json").exists()
        assert (out_dir / "comp1.png").exists()
        assert "images" not in res
        assert "annotated_images" not in res

