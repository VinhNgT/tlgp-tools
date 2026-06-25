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
        logger.info(
            "DaemonManager initialized with workspace root: %s", self.workspace_root
        )

        # In-memory log buffers
        self.annotator_logs: deque[str] = deque(maxlen=log_maxlen)

        # Active process tracking
        self.active_processes: list[subprocess.Popen] = []

        # Target annotator URL
        self.annotator_url = os.environ.get(
            "TLGP_ANNOTATOR_URL", "http://127.0.0.1:8000"
        ).rstrip("/")

    def cleanup(self) -> None:
        """Terminate all active background processes."""
        for proc in self.active_processes:
            try:
                proc.terminate()
            except Exception as e:
                logger.warning("Failed to terminate process %s: %s", proc.pid, e)
        self.active_processes.clear()

    def _pipe_stream(
        self,
        stream,
        log_deque,
        dest_stream,
        port_future: asyncio.Future | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Pipe lines from stream to the log deque and write atomic output to dest_stream."""
        try:
            for line in iter(stream.readline, b""):
                decoded = line.decode("utf-8", errors="replace")
                log_deque.append(decoded)

                # Check for port reporting
                if (
                    port_future is not None
                    and loop is not None
                    and not port_future.done()
                ):
                    if decoded.startswith("PORT="):
                        try:
                            port_num = int(decoded.strip().split("=")[1])
                            loop.call_soon_threadsafe(port_future.set_result, port_num)
                        except ValueError:
                            pass

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

    async def launch_annotator(
        self,
        path: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        """Spawn the monolithic annotation tool as a background subprocess."""
        if not self.uv_bin:
            raise RuntimeError("uv is not installed or not on PATH")

        env = os.environ.copy()

        annotator_dir = os.path.join(self.workspace_root, "apps", "annotator")

        logger.info("Spawning annotator daemon under Cwd: %s", annotator_dir)
        annotator_cmd = [self.uv_bin, "run", "annotator"]
        if path:
            annotator_cmd.append(os.path.abspath(path))

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

        loop = asyncio.get_running_loop()
        port_future = loop.create_future()

        # Start background stream pipe threads
        threading.Thread(
            target=self._pipe_stream,
            args=(
                annotator_proc.stdout,
                self.annotator_logs,
                sys.stderr,
                port_future,
                loop,
            ),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_stream,
            args=(
                annotator_proc.stderr,
                self.annotator_logs,
                sys.stderr,
                port_future,
                loop,
            ),
            daemon=True,
        ).start()

        # Wait for the PORT line in the logs
        logger.info("Waiting for Annotator port reporting...")
        try:
            port_num = await asyncio.wait_for(port_future, timeout=5.0)
        except TimeoutError:
            logger.error(
                "Annotator failed to report PORT via stdout. Defaulting to 8000."
            )
            port_num = 8000

        self.annotator_url = f"http://127.0.0.1:{port_num}"
        logger.info("Detected Annotator port: %s", port_num)

        # Wait for the Annotator's HTTP API to become ready
        annotator_ready = False
        logger.info("Polling Annotator HTTP readiness at %s...", self.annotator_url)

        # Use provided client or short-lived client
        async def poll_readiness(c: httpx.AsyncClient) -> bool:
            for _ in range(30):
                try:
                    res = await c.get(f"{self.annotator_url}/health")
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
            logger.info("Annotator HTTP API ready.")

        return {
            "annotator_url": self.annotator_url,
            "annotator_ready": annotator_ready,
        }
