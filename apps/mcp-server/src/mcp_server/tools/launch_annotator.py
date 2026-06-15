"""Tool: launch_annotator — spawn the TLGP annotation tool GUI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import asyncio

import httpx


async def launch_annotator_impl(
    screenshot_path: str | None = None,
    workspace_zip: str | None = None,
) -> dict:
    """Spawn the annotation tool as a background subprocess.

    Constructs a command line equivalent to:
        uv run python -m tlgp_annotation_tool [screenshot] -o <output_dir>
        uv run python -m tlgp_annotation_tool -s <session.json> -o <output_dir>

    Uses ``uv run`` instead of ``sys.executable`` so the annotation tool
    resolves correctly from the uv workspace regardless of which Python
    interpreter the MCP server was started with.

    The process is detached so it doesn't block the MCP server.
    """
    if screenshot_path and workspace_zip:
        raise ValueError("screenshot_path and workspace_zip are mutually exclusive")

    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv is not installed or not on PATH")

    import secrets
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
    
    api_key = secrets.token_hex(16)
    env = os.environ.copy()
    env["ENGINE_API_KEY"] = api_key

    # Spawn Engine
    engine_cmd = [uv_bin, "run", "python", "-m", "engine"]
    engine_proc = subprocess.Popen(
        engine_cmd,
        cwd=os.path.join(workspace_root, "apps", "engine"),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        stderr=sys.stderr,
        start_new_session=True,
    )

    # Spawn GUI
    gui_cmd = [uv_bin, "run", "python", "-m", "gui"]
    gui_proc = subprocess.Popen(
        gui_cmd,
        cwd=os.path.join(workspace_root, "apps", "gui"),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        stderr=sys.stderr,
        start_new_session=True,
    )

    # Wait for Engine to be ready
    engine_ready = False
    
    async with httpx.AsyncClient() as client:
        for _ in range(30):  # Wait up to 3 seconds
            try:
                res = await client.get("http://127.0.0.1:8000/workspace/state")
                if res.status_code == 200:
                    engine_ready = True
                    break
            except httpx.RequestError:
                pass
            await asyncio.sleep(0.1)

        if engine_ready:
            headers = {"X-API-Key": api_key}
            if screenshot_path:
                with open(os.path.abspath(screenshot_path), "rb") as f:
                    await client.post("http://127.0.0.1:8000/workspace/import-image", files={"file": f}, headers=headers)
            elif workspace_zip:
                with open(os.path.abspath(workspace_zip), "rb") as f:
                    await client.post("http://127.0.0.1:8000/workspace/import", files={"file": f}, headers=headers)

    return {
        "engine_pid": engine_proc.pid,
        "gui_pid": gui_proc.pid,
        "engine_ready": engine_ready,
    }
