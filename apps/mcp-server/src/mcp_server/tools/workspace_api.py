import os
import io
import zipfile
import httpx
from mcp_server.exceptions import ApiClientError

async def get_workspace_state_impl() -> dict:
    """Implementation of get_workspace_state tool."""
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://127.0.0.1:8000/workspace/state")
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="Failed to fetch workspace state",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request to fetch workspace state failed: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e


async def download_image_impl(comp_id: str, output_path: str, show_children: bool = False) -> dict:
    """Implementation of download_image tool."""
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"http://127.0.0.1:8000/images/{comp_id}",
                params={"show_children": show_children}
            )
            res.raise_for_status()
            
            out_path = os.path.abspath(output_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(res.content)
                
            return {
                "status": "success",
                "output_path": out_path
            }
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message=f"HTTP error while downloading image {comp_id}",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request failed while downloading image {comp_id}: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e


async def download_workspace_assets_impl(
    output_dir: str,
    include_state: bool = True,
    include_root: bool = True,
    show_root_children: bool = False,
    component_ids: list[str] | None = None,
    show_component_children: bool = False,
) -> dict:
    """Implementation of download_workspace_assets tool."""
    out_path = os.path.abspath(output_dir)
    os.makedirs(out_path, exist_ok=True)

    try:
        async with httpx.AsyncClient() as client:
            # 1. Resolve component IDs if None (download all)
            if component_ids is None:
                state_res = await client.get("http://127.0.0.1:8000/workspace/state")
                state_res.raise_for_status()
                state = state_res.json()
                component_ids = list(state.get("components", {}).keys())

            # 2. Build the payload
            payload = {
                "include_state": include_state,
                "include_root": include_root,
                "show_root_children": show_root_children,
                "components": [
                    {"id": comp_id, "show_children": show_component_children}
                    for comp_id in component_ids
                ]
            }

            # 3. Call the POST export-batch endpoint
            res = await client.post(
                "http://127.0.0.1:8000/workspace/export-batch",
                json=payload
            )
            res.raise_for_status()

            # 4. Extract the ZIP in memory to the output directory
            zip_buf = io.BytesIO(res.content)
            with zipfile.ZipFile(zip_buf, "r") as zf:
                zf.extractall(out_path)

            return {
                "status": "success",
                "output_dir": out_path,
                "extracted_files": os.listdir(out_path)
            }
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="HTTP error while downloading workspace assets",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request failed while downloading workspace assets: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e


async def export_workspace_impl(output_path: str) -> dict:
    """Implementation of export_workspace tool."""
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://127.0.0.1:8000/workspace/export")
            res.raise_for_status()
            
            out_path = os.path.abspath(output_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(res.content)
                
            return {
                "status": "success",
                "output_path": out_path
            }
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="HTTP error while exporting workspace",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request failed while exporting workspace: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e
