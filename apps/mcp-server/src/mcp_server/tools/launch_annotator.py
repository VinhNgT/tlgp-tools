"""Tool: launch_annotator — spawn the TLGP annotation tool GUI and engine."""

from __future__ import annotations

import asyncio
import os

import shutil
import subprocess
import sys
import threading

import httpx

import mcp_server.tools.daemon_control as dc
from mcp_server.tools.daemon_control import ACTIVE_PROCESSES, ENGINE_LOGS, GUI_LOGS


def _pipe_stream(stream, log_deque, dest_stream):
    """Drain stream line-by-line, append to log_deque, and write to dest_stream."""
    try:
        for line in iter(stream.readline, b""):
            decoded = line.decode("utf-8", errors="replace")
            log_deque.append(decoded)
            dest_stream.write(decoded)
            dest_stream.flush()
    except Exception:
        pass
    finally:
        stream.close()


async def launch_annotator_impl(
    screenshot_path: str | None = None,
    workspace_zip: str | None = None,
) -> dict:
    """Spawn the annotation tool and engine as background subprocesses.

    Pipes stdout/stderr to in-memory log deques and mirrors them to sys.stderr.
    Registers process handles for lifecycle management and automatic cleanup on exit.
    """
    if screenshot_path and workspace_zip:
        raise ValueError("screenshot_path and workspace_zip are mutually exclusive")

    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv is not installed or not on PATH")

    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))

    env = os.environ.copy()

    # Spawn Engine
    engine_cmd = [uv_bin, "run", "python", "-m", "engine"]
    engine_proc = subprocess.Popen(
        engine_cmd,
        cwd=os.path.join(workspace_root, "apps", "engine"),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Spawn GUI
    gui_cmd = [uv_bin, "run", "python", "-m", "gui"]
    gui_proc = subprocess.Popen(
        gui_cmd,
        cwd=os.path.join(workspace_root, "apps", "gui"),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Register active processes
    ACTIVE_PROCESSES.append(engine_proc)
    ACTIVE_PROCESSES.append(gui_proc)

    # Start piping threads
    threading.Thread(target=_pipe_stream, args=(engine_proc.stdout, ENGINE_LOGS, sys.stderr), daemon=True).start()
    threading.Thread(target=_pipe_stream, args=(engine_proc.stderr, ENGINE_LOGS, sys.stderr), daemon=True).start()
    threading.Thread(target=_pipe_stream, args=(gui_proc.stdout, GUI_LOGS, sys.stderr), daemon=True).start()
    threading.Thread(target=_pipe_stream, args=(gui_proc.stderr, GUI_LOGS, sys.stderr), daemon=True).start()

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
            if screenshot_path:
                with open(os.path.abspath(screenshot_path), "rb") as f:
                    await client.post("http://127.0.0.1:8000/workspace/import-image", files={"file": f})
            elif workspace_zip:
                with open(os.path.abspath(workspace_zip), "rb") as f:
                    await client.post("http://127.0.0.1:8000/workspace/import", files={"file": f})

    return {
        "engine_pid": engine_proc.pid,
        "gui_pid": gui_proc.pid,
        "engine_ready": engine_ready,
    }
