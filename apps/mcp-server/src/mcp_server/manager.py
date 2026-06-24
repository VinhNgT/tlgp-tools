"""Manager for background daemon processes (annotator)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import threading
from collections import deque

import httpx
from tlgp_logger import get_logger

logger = get_logger(__name__)

# Thread-safe lock for standard stream output mirroring
STDERR_LOCK = threading.Lock()


class DaemonManager:
    """Manages the lifecycle, execution, status, and logging of background daemons.

    Maintains in-memory log deques.
    """

    def __init__(
        self,
        workspace_root: str | None = None,
        uv_bin: str | None = None,
        log_maxlen: int = 500,
    ):
        """Initialize DaemonManager with configurable paths.

        Args:
            workspace_root: Path to the tlgp-tools repository root. If None, checks the
                TLGP_WORKSPACE_ROOT env variable, falling back to dynamic parent traversal.
            uv_bin: Path to the 'uv' binary. If None, resolves using system PATH.
            log_maxlen: Maximum lines to retain in in-memory logs.
        """
        # Resolve UV binary path
        self.uv_bin = uv_bin or shutil.which("uv")

        # Resolve workspace root directory
        if not workspace_root:
            workspace_root = os.environ.get("TLGP_WORKSPACE_ROOT")
        if not workspace_root:
            manager_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_root = os.path.abspath(os.path.join(manager_dir, "../../../.."))

        self.workspace_root = workspace_root
        logger.info("DaemonManager initialized with workspace root: %s", self.workspace_root)

        # In-memory log buffers
        self.annotator_logs: deque[str] = deque(maxlen=log_maxlen)

        # Active process tracking
        self.active_processes: list[subprocess.Popen] = []

    def _pipe_stream(self, stream, log_deque, dest_stream) -> None:
        """Pipe lines from stream to the log deque and write atomic output to dest_stream."""
        try:
            for line in iter(stream.readline, b""):
                decoded = line.decode("utf-8", errors="replace")
                log_deque.append(decoded)
                with STDERR_LOCK:
                    dest_stream.write(decoded)
                    dest_stream.flush()
        except Exception as e:
            logger.debug("Stream pipe exception encountered: %s", e)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    async def get_status(self, client: httpx.AsyncClient | None = None) -> dict:
        """Retrieve the running status of the annotator process."""
        annotator_running = False
        annotator_ready = False

        # 1. Check process list status
        for proc in list(self.active_processes):
            if proc.poll() is None:
                cmd = proc.args
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "annotator" in cmd_str:
                    annotator_running = True

        # 2. Check annotator HTTP readiness
        # If client is passed, use it, otherwise instantiate a short-lived client
        annotator_url = os.environ.get("TLGP_ANNOTATOR_URL", "http://127.0.0.1:8000").rstrip("/")
        try:
            if client is not None:
                res = await client.get(f"{annotator_url}/workspace/state", timeout=0.5)
                if res.status_code == 200:
                    annotator_ready = True
                    annotator_running = True
            else:
                async with httpx.AsyncClient() as c:
                    res = await c.get(f"{annotator_url}/workspace/state", timeout=0.5)
                    if res.status_code == 200:
                        annotator_ready = True
                        annotator_running = True
        except Exception:
            pass

        return {
            "annotator": {
                "running": annotator_running,
                "ready": annotator_ready,
            }
        }


    def read_daemon_logs(self, daemon: str = "annotator", lines: int = 100) -> dict:
        """Read requested tailing lines from the selected daemon's log buffer."""
        # Both map to annotator_logs now
        buf = self.annotator_logs

        snapshot = list(buf)
        requested_logs = snapshot[-lines:] if lines > 0 else snapshot

        return {
            "daemon": daemon,
            "line_count": len(requested_logs),
            "logs": "".join(requested_logs),
        }

    async def launch_annotator(
        self,
        screenshot_path: str | None = None,
        workspace_zip: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        """Spawn the monolithic annotation tool as a background subprocess."""
        if screenshot_path and workspace_zip:
            raise ValueError("screenshot_path and workspace_zip are mutually exclusive")

        if not self.uv_bin:
            raise RuntimeError("uv is not installed or not on PATH")

        env = os.environ.copy()

        annotator_dir = os.path.join(self.workspace_root, "apps", "annotator")

        logger.info("Spawning annotator daemon under Cwd: %s", annotator_dir)
        annotator_cmd = [self.uv_bin, "run", "annotator"]
        annotator_proc = subprocess.Popen(
            annotator_cmd,
            cwd=annotator_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        self.active_processes.append(annotator_proc)

        # Start background stream pipe threads
        threading.Thread(
            target=self._pipe_stream,
            args=(annotator_proc.stdout, self.annotator_logs, sys.stderr),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_stream,
            args=(annotator_proc.stderr, self.annotator_logs, sys.stderr),
            daemon=True,
        ).start()

        # Wait for the Annotator's HTTP API to become ready
        annotator_ready = False
        annotator_url = os.environ.get("TLGP_ANNOTATOR_URL", "http://127.0.0.1:8000").rstrip("/")

        logger.info("Polling Annotator HTTP readiness at %s...", annotator_url)
        # Use provided client or short-lived client
        async def poll_readiness(c: httpx.AsyncClient) -> bool:
            for _ in range(30):
                try:
                    res = await c.get(f"{annotator_url}/workspace/state")
                    if res.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            return False

        if client is not None:
            annotator_ready = await poll_readiness(client)
        else:
            async with httpx.AsyncClient() as c:
                annotator_ready = await poll_readiness(c)

        if not annotator_ready:
            logger.error("Annotator failed to become ready after 3 seconds.")
        else:
            logger.info("Annotator HTTP API ready. Importing initial assets...")
            if screenshot_path:
                abs_screenshot = os.path.abspath(screenshot_path)
                with open(abs_screenshot, "rb") as f:
                    if client is not None:
                        await client.post(f"{annotator_url}/workspace/import-image", files={"file": f})
                    else:
                        async with httpx.AsyncClient() as c:
                            await c.post(f"{annotator_url}/workspace/import-image", files={"file": f})
            elif workspace_zip:
                abs_zip = os.path.abspath(workspace_zip)
                with open(abs_zip, "rb") as f:
                    if client is not None:
                        await client.post(f"{annotator_url}/workspace/import", files={"file": f})
                    else:
                        async with httpx.AsyncClient() as c:
                            await c.post(f"{annotator_url}/workspace/import", files={"file": f})

        return {
            "annotator_pid": annotator_proc.pid,
            "annotator_ready": annotator_ready,
        }
