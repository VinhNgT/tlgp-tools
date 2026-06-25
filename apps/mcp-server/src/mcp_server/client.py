"""Client for communicating with the TLGP Annotator API."""

from __future__ import annotations

import io
import json
import os
import zipfile

import httpx
from tlgp_logger import get_logger

from mcp_server.exceptions import ApiClientError

logger = get_logger(__name__)


class WorkspaceClient:
    """A thread-safe API client for communicating with the TLGP Annotator REST API.

    Shares a single, reusable httpx.AsyncClient instance.
    """

    def __init__(
        self, base_url: str | None = None, client: httpx.AsyncClient | None = None
    ):
        """Initialize the client.

        Args:
            base_url: Base URL of the Annotator API. If not set, checks the TLGP_ANNOTATOR_URL
                environment variable, falling back to 'http://127.0.0.1:8000'.
            client: An optional pre-configured AsyncClient. If None, an AsyncClient is
                instantiated lazily.
        """
        self.base_url = (
            base_url or os.environ.get("TLGP_ANNOTATOR_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.AsyncClient:
        """Retrieve the shared AsyncClient, initializing it lazily if necessary."""
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        """Close the underlying client session if owned by this instance."""
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Perform an HTTP request with error wrapping and logging."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.debug("Executing HTTP %s request to %s", method, url)
        try:
            res = await self.client.request(method, url, **kwargs)
            res.raise_for_status()
            return res
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error %s returned from %s %s: %s",
                e.response.status_code,
                method,
                url,
                e.response.text,
            )
            raise ApiClientError(
                message=f"HTTP status error during {method} {path}",
                status_code=e.response.status_code,
                url=str(e.request.url),
                method=e.request.method,
                backend_detail=e.response.text,
            ) from e
        except httpx.RequestError as e:
            logger.error("Request failed for %s %s: %s", method, url, e)
            raise ApiClientError(
                message=f"Network/request error during {method} {path}: {e}",
                url=str(e.request.url) if hasattr(e, "request") else None,
                method=e.request.method if hasattr(e, "request") else None,
            ) from e

    async def get_workspace_state(self) -> dict:
        """Fetch the current flat-map JSON WorkspaceState from the running Annotator."""
        res = await self._request("GET", "/workspace/state")
        return res.json()

    async def check_connection(self) -> bool:
        """Verify the connection is active using the lightweight /health endpoint."""
        try:
            res = await self._request("GET", "/health")
            return res.json().get("status") == "ok"
        except Exception:
            return False


    async def export_workspace(self, output_path: str) -> dict:
        """Export the current workspace (state JSON and raw screenshot) as a zip file.

        Args:
            output_path: Absolute path to the output .zip file.
        """
        res = await self._request("GET", "/workspace/export")
        out_path = os.path.abspath(output_path)

        parent_dir = os.path.dirname(out_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(out_path, "wb") as f:
            f.write(res.content)

        return {
            "status": "success",
            "output_path": out_path,
        }

    async def export_images(
        self,
        output_path: str,
        mode: Literal["annotated", "raw", "both"] = "both",
    ) -> dict:
        """Export cropped component images from the workspace to a directory.

        Args:
            output_path: Directory path to extract the cropped images.
            mode: Export mode ('annotated', 'raw', or 'both').
        """
        res = await self._request(
            "GET", "/workspace/export-images", params={"mode": mode}
        )
        out_path = os.path.abspath(output_path)

        os.makedirs(out_path, exist_ok=True)
        zip_buf = io.BytesIO(res.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            zf.extractall(out_path)
        return {
            "status": "success",
            "output_dir": out_path,
            "exported_files": os.listdir(out_path),
        }
