"""Manager for background daemon processes (engine and gui)."""

from __future__ import annotations

import asyncio
import atexit
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

    Maintains in-memory log deques and ensures cleanup upon exit.
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
        self.engine_logs: deque[str] = deque(maxlen=log_maxlen)
        self.gui_logs: deque[str] = deque(maxlen=log_maxlen)

        # Active process tracking
        self.active_processes: list[subprocess.Popen] = []

    def register_exit_handlers(self) -> None:
        """Register process exit handlers to ensure cleanup upon system termination."""
        atexit.register(self.kill_daemons)

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
        """Retrieve the running status of engine and GUI processes."""
        engine_running = False
        gui_running = False
        engine_ready = False

        # 1. Check process list status
        for proc in list(self.active_processes):
            if proc.poll() is None:
                cmd = proc.args
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "engine" in cmd_str:
                    engine_running = True
                elif "gui" in cmd_str:
                    gui_running = True

        # 2. Check engine HTTP readiness
        # If client is passed, use it, otherwise instantiate a short-lived client
        engine_url = os.environ.get("TLGP_ENGINE_URL", "http://127.0.0.1:8000").rstrip("/")
        try:
            if client is not None:
                res = await client.get(f"{engine_url}/workspace/state", timeout=0.5)
                if res.status_code == 200:
                    engine_ready = True
                    engine_running = True
            else:
                async with httpx.AsyncClient() as c:
                    res = await c.get(f"{engine_url}/workspace/state", timeout=0.5)
                    if res.status_code == 200:
                        engine_ready = True
                        engine_running = True
        except Exception:
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

    def kill_daemons(self) -> dict:
        """Cleanly terminate all tracked running processes."""
        terminated = []
        killed = []

        logger.info("Terminating all active daemon subprocesses...")
        for proc in list(self.active_processes):
            if proc.poll() is None:
                pid = proc.pid
                try:
                    proc.terminate()
                    proc.wait(timeout=1.0)
                    terminated.append(pid)
                    logger.info("Successfully terminated daemon process PID %s", pid)
                except subprocess.TimeoutExpired:
                    try:
                        logger.warning("Daemon PID %s did not terminate in time. Killing it...", pid)
                        proc.kill()
                        proc.wait()
                        killed.append(pid)
                    except Exception as e:
                        logger.error("Failed to kill process PID %s: %s", pid, e)
                except Exception as e:
                    logger.error("Failed to terminate process PID %s: %s", pid, e)

        self.active_processes.clear()
        return {
            "status": "success",
            "terminated_pids": terminated,
            "killed_pids": killed,
        }

    def read_daemon_logs(self, daemon: str = "engine", lines: int = 100) -> dict:
        """Read requested tailing lines from the selected daemon's log buffer."""
        if daemon == "engine":
            buf = self.engine_logs
        elif daemon == "gui":
            buf = self.gui_logs
        else:
            raise ValueError(f"Unknown daemon: '{daemon}'. Must be 'engine' or 'gui'.")

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
        """Spawn the annotation tool engine and GUI as background subprocesses."""
        if screenshot_path and workspace_zip:
            raise ValueError("screenshot_path and workspace_zip are mutually exclusive")

        if not self.uv_bin:
            raise RuntimeError("uv is not installed or not on PATH")

        env = os.environ.copy()

        engine_dir = os.path.join(self.workspace_root, "apps", "engine")
        gui_dir = os.path.join(self.workspace_root, "apps", "gui")

        logger.info("Spawning engine daemon under Cwd: %s", engine_dir)
        engine_cmd = [self.uv_bin, "run", "python", "-m", "engine"]
        engine_proc = subprocess.Popen(
            engine_cmd,
            cwd=engine_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        logger.info("Spawning GUI daemon under Cwd: %s", gui_dir)
        gui_cmd = [self.uv_bin, "run", "python", "-m", "gui"]
        gui_proc = subprocess.Popen(
            gui_cmd,
            cwd=gui_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        self.active_processes.append(engine_proc)
        self.active_processes.append(gui_proc)

        # Start background stream pipe threads
        threading.Thread(
            target=self._pipe_stream,
            args=(engine_proc.stdout, self.engine_logs, sys.stderr),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_stream,
            args=(engine_proc.stderr, self.engine_logs, sys.stderr),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_stream,
            args=(gui_proc.stdout, self.gui_logs, sys.stderr),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_stream,
            args=(gui_proc.stderr, self.gui_logs, sys.stderr),
            daemon=True,
        ).start()

        # Wait for the Engine's HTTP API to become ready
        engine_ready = False
        engine_url = os.environ.get("TLGP_ENGINE_URL", "http://127.0.0.1:8000").rstrip("/")

        logger.info("Polling Engine HTTP readiness at %s...", engine_url)
        # Use provided client or short-lived client
        async def poll_readiness(c: httpx.AsyncClient) -> bool:
            for _ in range(30):
                try:
                    res = await c.get(f"{engine_url}/workspace/state")
                    if res.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            return False

        if client is not None:
            engine_ready = await poll_readiness(client)
        else:
            async with httpx.AsyncClient() as c:
                engine_ready = await poll_readiness(c)

        if not engine_ready:
            logger.error("Engine failed to become ready after 3 seconds.")
        else:
            logger.info("Engine HTTP API ready. Importing initial assets...")
            if screenshot_path:
                abs_screenshot = os.path.abspath(screenshot_path)
                with open(abs_screenshot, "rb") as f:
                    if client is not None:
                        await client.post(f"{engine_url}/workspace/import-image", files={"file": f})
                    else:
                        async with httpx.AsyncClient() as c:
                            await c.post(f"{engine_url}/workspace/import-image", files={"file": f})
            elif workspace_zip:
                abs_zip = os.path.abspath(workspace_zip)
                with open(abs_zip, "rb") as f:
                    if client is not None:
                        await client.post(f"{engine_url}/workspace/import", files={"file": f})
                    else:
                        async with httpx.AsyncClient() as c:
                            await c.post(f"{engine_url}/workspace/import", files={"file": f})

        return {
            "engine_pid": engine_proc.pid,
            "gui_pid": gui_proc.pid,
            "engine_ready": engine_ready,
        }
