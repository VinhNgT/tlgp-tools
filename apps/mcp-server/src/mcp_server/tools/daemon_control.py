"""Tools for managing the lifecycle of background daemons (engine and gui)."""

from __future__ import annotations

import atexit
import os
import subprocess
from collections import deque

import httpx
from tlgp_logger import get_logger

from mcp_server.exceptions import ApiClientError

logger = get_logger(__name__)

# Global in-memory buffers
ENGINE_LOGS: deque[str] = deque(maxlen=500)
GUI_LOGS: deque[str] = deque(maxlen=500)

# Track active subprocesses (Popen instances)
ACTIVE_PROCESSES: list[subprocess.Popen] = []

# Store the active API key in-memory instead of mutating os.environ globally (avoids test contamination)
ENGINE_API_KEY: str | None = None


def register_exit_handlers():
    """Register exit handlers to clean up processes on exit."""
    atexit.register(kill_daemons_impl)


async def get_daemon_status_impl() -> dict:
    """Retrieve the running status of engine and GUI processes."""
    engine_running = False
    gui_running = False
    engine_ready = False

    # 1. Check process list status
    for proc in ACTIVE_PROCESSES:
        if proc.poll() is None:  # Still running
            # Check command line or identify process
            cmd = proc.args
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "engine" in cmd_str:
                engine_running = True
            elif "gui" in cmd_str:
                gui_running = True

    # 2. Check engine HTTP readiness
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://127.0.0.1:8000/workspace/state", timeout=0.5)
            if res.status_code == 200:
                engine_ready = True
                # If engine is responding, consider it running even if not in ACTIVE_PROCESSES
                engine_running = True
    except httpx.RequestError:
        pass

    return {
        "engine": {
            "running": engine_running,
            "ready": engine_ready,
        },
        "gui": {
            "running": gui_running,
        }
    }


def kill_daemons_impl() -> dict:
    """Cleanly terminate all running subprocesses."""
    terminated = []
    killed = []

    for proc in list(ACTIVE_PROCESSES):
        if proc.poll() is None:
            pid = proc.pid
            try:
                # On Windows, terminate() sends TerminateProcess.
                proc.terminate()
                proc.wait(timeout=1.0)
                terminated.append(pid)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait()
                    killed.append(pid)
                except Exception:
                    pass
            except Exception:
                pass

    # Clear the list
    ACTIVE_PROCESSES.clear()

    return {
        "status": "success",
        "terminated_pids": terminated,
        "killed_pids": killed,
    }


def read_daemon_logs_impl(daemon: str = "engine", lines: int = 100) -> dict:
    """Read the tail of the in-memory log buffer."""
    if daemon == "engine":
        buf = ENGINE_LOGS
    elif daemon == "gui":
        buf = GUI_LOGS
    else:
        raise ValueError(f"Unknown daemon: {daemon}. Must be 'engine' or 'gui'.")

    # Capture the snapshot of current logs
    log_snapshot = list(buf)
    # Get the last N lines
    requested_logs = log_snapshot[-lines:] if lines > 0 else log_snapshot

    return {
        "daemon": daemon,
        "line_count": len(requested_logs),
        "logs": "".join(requested_logs),
    }


async def set_workspace_readonly_impl(read_only: bool) -> dict:
    """Toggle the workspace read-only mode in the engine."""
    api_key = ENGINE_API_KEY or os.environ.get("ENGINE_API_KEY")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient() as client:
            res = await client.put(
                "http://127.0.0.1:8000/workspace/readonly",
                json={"read_only": read_only},
                headers=headers,
            )
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="Failed to toggle read-only mode",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request to toggle read-only mode failed: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e
