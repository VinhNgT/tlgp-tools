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

    async def download_image(
        self, comp_id: str, output_path: str, show_children: bool = False
    ) -> dict:
        """Download the full screenshot or a component image by extracting it from the export-images ZIP using mapping.json."""
        mode = "annotated" if show_children else "raw"
        res = await self._request("GET", "/workspace/export-images", params={"mode": mode})

        out_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        zip_buf = io.BytesIO(res.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            mapping = json.loads(zf.read("mapping.json").decode("utf-8"))

            if comp_id == "root":
                target_name = mapping.get("root")
            else:
                target_name = mapping.get("components", {}).get(comp_id)

            if not target_name:
                raise ApiClientError(
                    message=f"Component image not found in export archive mapping: {comp_id}",
                    url=None,
                    method="GET",
                )

            with open(out_path, "wb") as f:
                f.write(zf.read(target_name))

        return {"status": "success", "output_path": out_path}

    async def get_image_bytes(self, comp_id: str, show_children: bool = False) -> bytes:
        """Fetch the raw image bytes for a component by extracting it from the export-images ZIP using mapping.json."""
        mode = "annotated" if show_children else "raw"
        res = await self._request("GET", "/workspace/export-images", params={"mode": mode})

        zip_buf = io.BytesIO(res.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            mapping = json.loads(zf.read("mapping.json").decode("utf-8"))

            if comp_id == "root":
                target_name = mapping.get("root")
            else:
                target_name = mapping.get("components", {}).get(comp_id)

            if not target_name:
                raise ApiClientError(
                    message=f"Component image not found in export archive mapping: {comp_id}",
                    url=None,
                    method="GET",
                )

            return zf.read(target_name)

    async def export_workspace(self, output_path: str) -> dict:
        """Export the current workspace to a zip archive at output_path."""
        res = await self._request("GET", "/workspace/export")
        out_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(res.content)
        return {"status": "success", "output_path": out_path}

    async def download_workspace_assets(
        self,
        output_dir: str,
        include_state: bool = True,
        include_root: bool = True,
        show_root_children: bool = False,
        component_ids: list[str] | None = None,
        show_component_children: bool = False,
    ) -> dict:
        """Download all state and image assets for the current workspace in a single batch."""
        out_path = os.path.abspath(output_dir)
        os.makedirs(out_path, exist_ok=True)

        state = await self.get_workspace_state()

        if include_state:
            state_file = os.path.join(out_path, "workspace.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)

        # Download ZIP of all crops
        # We match show_root_children/show_component_children to the modes
        mode = "annotated" if (show_root_children or show_component_children) else "raw"
        res = await self._request("GET", "/workspace/export-images", params={"mode": mode})

        zip_buf = io.BytesIO(res.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            mapping = json.loads(zf.read("mapping.json").decode("utf-8"))

            # Extract root image if requested
            if include_root:
                root_name = mapping.get("root")
                if root_name:
                    with open(os.path.join(out_path, "raw.png"), "wb") as f:
                        f.write(zf.read(root_name))

            # Extract component images
            images_dir = os.path.join(out_path, "images")
            os.makedirs(images_dir, exist_ok=True)

            if component_ids is None:
                component_ids = list(state.get("components", {}).keys())

            for comp_id in component_ids:
                target_name = mapping.get("components", {}).get(comp_id)
                if target_name:
                    with open(os.path.join(images_dir, f"{comp_id}.png"), "wb") as f:
                        f.write(zf.read(target_name))

        return {
            "status": "success",
            "output_dir": out_path,
            "extracted_files": os.listdir(out_path),
        }
