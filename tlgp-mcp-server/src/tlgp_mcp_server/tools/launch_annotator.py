"""Tool: launch_annotator — spawn the TLGP annotation tool GUI."""

from __future__ import annotations

import os
import shutil
import subprocess


def launch_annotator_impl(
    output_dir: str,
    screenshot_path: str | None = None,
    session_path: str | None = None,
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
    if screenshot_path and session_path:
        raise ValueError("screenshot_path and session_path are mutually exclusive")

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv is not installed or not on PATH")

    cmd = [uv_bin, "run", "python", "-m", "tlgp_annotation_tool"]
    if screenshot_path:
        cmd.append(os.path.abspath(screenshot_path))
    if session_path:
        cmd.extend(["-s", os.path.abspath(session_path)])
    cmd.extend(["-o", output_dir])

    # Spawn detached — don't wait for the GUI to close
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return {
        "pid": proc.pid,
    }
