"""Tool: launch_annotator — spawn the TLGP annotation tool GUI."""

from __future__ import annotations

import os
import subprocess
import sys


def launch_annotator_impl(
    output_dir: str,
    screenshot_paths: list[str] | None = None,
) -> dict:
    """Spawn the annotation tool as a background subprocess.

    Constructs a command line equivalent to:
        python -m tlgp_annotation_tool [screenshots...] -o <output_dir>

    The process is detached so it doesn't block the MCP server.
    """
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    cmd = [sys.executable, "-m", "tlgp_annotation_tool"]
    if screenshot_paths:
        for p in screenshot_paths:
            cmd.append(os.path.abspath(p))
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
        "output_dir": output_dir,
        "message": (
            "Annotation tool launched. The user will annotate screenshots "
            "and export when finished. Wait for the user to confirm they "
            "are done before proceeding."
        ),
    }
