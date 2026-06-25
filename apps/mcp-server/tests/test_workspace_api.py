"""Tests for the WorkspaceClient API methods."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.exceptions import ApiClientError


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
    async def test_get_workspace_state_success(self, monkeypatch):
        class MockResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"version": 1, "sessionId": "abc"}

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                # We mock HTTP request method
                assert method == "GET"
                assert "workspace/state" in url
                return MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        client = WorkspaceClient()
        res = await client.get_workspace_state()
        assert res["version"] == 1
        assert res["sessionId"] == "abc"

    @pytest.mark.anyio
    async def test_get_workspace_state_http_status_error(self, monkeypatch):
        req = httpx.Request("GET", "http://localhost/state")
        resp = httpx.Response(404, request=req, text="Not found details")

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                raise httpx.HTTPStatusError("Not Found", request=req, response=resp)

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

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
    async def test_get_workspace_state_request_error(self, monkeypatch):
        req = httpx.Request("GET", "http://localhost/state")

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                raise httpx.RequestError("Connection refused", request=req)

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        client = WorkspaceClient()
        with pytest.raises(ApiClientError) as exc_info:
            await client.get_workspace_state()

        err = exc_info.value
        assert "Connection refused" in err.message
        assert err.status_code is None
        assert err.url is not None
        assert "localhost/state" in err.url

    @pytest.mark.anyio
    async def test_download_image_success(self, tmp_path, monkeypatch):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("images/compuuid.png", b"fake_png_data")
            zf.writestr("mapping.json", '{"root": "root_raw.png", "components": {"comp-uuid": "images/compuuid.png"}}')

        class MockResponse:
            status_code = 200
            content = zip_buf.getvalue()

            def raise_for_status(self):
                pass

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                assert method == "GET"
                assert "workspace/export-images" in url
                return MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        out_file = tmp_path / "images" / "output.png"
        client = WorkspaceClient()
        res = await client.download_image("comp-uuid", str(out_file))

        assert res["status"] == "success"
        assert Path(res["output_path"]).exists()
        assert Path(res["output_path"]).read_bytes() == b"fake_png_data"

    @pytest.mark.anyio
    async def test_download_workspace_assets_success(self, tmp_path, monkeypatch):
        # 1. Create a dummy in-memory zip containing workspace assets
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("root_raw.png", b"image_bytes")
            zf.writestr("images/comp1.png", b"comp_bytes")
            zf.writestr("mapping.json", '{"root": "root_raw.png", "components": {"comp1": "images/comp1.png"}}')

        class MockResponse:
            status_code = 200
            content = zip_buf.getvalue()

            def raise_for_status(self):
                pass

            def json(self):
                # When get_workspace_state is called internally if component_ids is None
                return {"components": {"comp1": {}}}

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                assert method == "GET"
                if "workspace/state" in url:
                    pass
                elif "workspace/export-images" in url:
                    pass
                else:
                    raise AssertionError(f"Unexpected GET URL: {url}")
                return MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        out_dir = tmp_path / "extracted_assets"
        client = WorkspaceClient()
        res = await client.download_workspace_assets(
            output_dir=str(out_dir),
            include_state=True,
            include_root=True,
            component_ids=None,
        )

        assert res["status"] == "success"
        assert (out_dir / "workspace.json").exists()
        assert (out_dir / "raw.png").exists()
        assert (out_dir / "images" / "comp1.png").exists()
        assert "workspace.json" in res["extracted_files"]

    @pytest.mark.anyio
    async def test_export_workspace_success(self, tmp_path, monkeypatch):
        class MockResponse:
            status_code = 200
            content = b"zip_bytes"

            def raise_for_status(self):
                pass

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                assert method == "GET"
                assert "workspace/export" in url
                return MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        out_zip = tmp_path / "exports" / "workspace.zip"
        client = WorkspaceClient()
        res = await client.export_workspace(str(out_zip))

        assert res["status"] == "success"
        assert Path(res["output_path"]).exists()
        assert Path(res["output_path"]).read_bytes() == b"zip_bytes"

    @pytest.mark.anyio
    async def test_get_image_bytes_success(self, monkeypatch):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("images/compuuid.png", b"raw_bytes")
            zf.writestr("mapping.json", '{"root": "root_raw.png", "components": {"comp-uuid": "images/compuuid.png"}}')

        class MockResponse:
            status_code = 200
            content = zip_buf.getvalue()

            def raise_for_status(self):
                pass

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def request(self, method, url, *args, **kwargs):
                assert method == "GET"
                assert "workspace/export-images" in url
                return MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

        client = WorkspaceClient()
        res = await client.get_image_bytes("comp-uuid")
        assert res == b"raw_bytes"


