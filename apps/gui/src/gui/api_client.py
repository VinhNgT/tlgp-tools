import asyncio
import json
import threading
import uuid
from collections.abc import Callable

import jsonpatch
import requests
import websockets
from models import WorkspaceState
from tlgp_logger import get_logger

API_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws"

logger = get_logger(__name__)


class ApiClientError(Exception):
    """Raised when an API request to the engine backend fails.

    Carries rich diagnostic metadata including the status code, URL, and server details.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_detail: str | None = None,
        url: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_detail = response_detail
        self.url = url
        self.details = details

    def __str__(self):
        parts = [self.message]
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        if self.response_detail:
            parts.append(f"Detail: {self.response_detail}")
        if self.details:
            parts.append(f"Context: {self.details}")
        if self.url:
            parts.append(f"URL: {self.url}")
        return " | ".join(parts)


class EngineClient:
    """Handles all REST and WebSocket communication with the backend FastAPI engine.

    Maintains a local copy of the WorkspaceState, which is kept in sync via JSON Patches.
    """

    def __init__(
        self,
        on_state_changed: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
        api_url: str = API_URL,
        ws_url: str = WS_URL,
    ):
        self.state: WorkspaceState | None = None
        self._state_dict: dict | None = None
        self.on_state_changed = on_state_changed
        self.on_error = on_error
        self.api_url = api_url
        self.ws_url = ws_url
        self._ws = None
        self._loop = None
        self._thread = None

    def start(self):
        """Starts the background event loop and WebSocket connection task."""
        if self._thread and self._thread.is_alive():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Cleanly cancels all tasks, stops the background event loop, and joins the thread."""
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(self._cancel_all_tasks)
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._loop = None

    def _cancel_all_tasks(self):
        for task in asyncio.all_tasks(self._loop):
            task.cancel()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen_ws())
        except asyncio.CancelledError:
            logger.info("EngineClient event loop cancelled successfully")
        except Exception:
            logger.exception("EngineClient event loop encountered an exception")
        finally:
            self._loop.close()

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("Connected to Engine WebSocket")
                    self._ws = ws
                    async for message in ws:
                        data = json.loads(message)

                        if "error" in data:
                            err_msg = data["error"].get("message", "Unknown error")
                            logger.error(
                                "JSON-RPC error response from engine", error=err_msg
                            )
                            if self.on_error:
                                self.on_error(err_msg)

                        elif data.get("type") == "full_sync":
                            self._state_dict = data["state"]
                            self.state = WorkspaceState.model_validate(self._state_dict)
                            self._trigger_update()

                        elif data.get("type") == "patch":
                            if self._state_dict is not None:
                                patch = jsonpatch.JsonPatch(data["patch"])
                                self._state_dict = patch.apply(self._state_dict)
                                self.state = WorkspaceState.model_validate(self._state_dict)
                                self._trigger_update()
            except asyncio.CancelledError:
                logger.info("WebSocket listener connection task cancelled")
                raise
            except Exception as e:
                logger.error("WS Connection lost, retrying in 2s...", error=str(e))
                self._ws = None
                self.state = None
                self._state_dict = None
                self._trigger_update()
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    raise

    def _trigger_update(self):
        # Fire callback safely (GUI must handle thread safety if needed)
        if self.on_state_changed:
            self.on_state_changed()

    async def _send_json_rpc(self, method: str, params: dict):
        if not self._ws:
            logger.warning(
                "WS not connected, cannot send JSON-RPC message", method=method
            )
            return None
        req_id = str(uuid.uuid4())
        msg = {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.error(
                "Failed to send JSON-RPC message over WebSocket",
                method=method,
                error=str(e),
            )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Centralized helper for HTTP requests to standardise error handling and exception logging."""
        try:
            res = requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            raise ApiClientError(f"Connection failed: {e}", url=url) from e

        if not (200 <= res.status_code < 300):
            detail = None
            details_ctx = None
            try:
                data = res.json()
                detail = data.get("detail")
                details_ctx = data.get("details")
            except Exception:
                pass

            raise ApiClientError(
                message=f"Request failed: {res.reason}",
                status_code=res.status_code,
                response_detail=detail or res.text,
                url=url,
                details=details_ctx,
            )
        return res

    # ── Async REST API Methods ──────────────────────────────────────────

    def import_zip(
        self,
        zip_path: str,
        on_complete: Callable[[Exception | None], None] | None = None,
    ):
        def job():
            try:
                with open(zip_path, "rb") as f:
                    self._request("POST", f"{self.api_url}/import", files={"file": f})
                if on_complete:
                    on_complete(None)
            except Exception as e:
                logger.exception("Failed to import zip in background")
                if on_complete:
                    on_complete(e)

        self._loop.call_soon_threadsafe(lambda: self._loop.run_in_executor(None, job))

    def import_image(
        self,
        image_path: str,
        on_complete: Callable[[Exception | None], None] | None = None,
    ):
        def job():
            try:
                with open(image_path, "rb") as f:
                    self._request("POST", f"{self.api_url}/import/image", files={"file": f})
                if on_complete:
                    on_complete(None)
            except Exception as e:
                logger.exception("Failed to import image in background")
                if on_complete:
                    on_complete(e)

        self._loop.call_soon_threadsafe(lambda: self._loop.run_in_executor(None, job))

    def export_zip_data(
        self, on_complete: Callable[[Exception | None, bytes | None], None]
    ):
        def job():
            try:
                res = self._request("GET", f"{self.api_url}/export")
                on_complete(None, res.content)
            except Exception as e:
                logger.exception("Failed to export zip in background")
                on_complete(e, None)

        self._loop.call_soon_threadsafe(lambda: self._loop.run_in_executor(None, job))

    # ── WebSocket JSON-RPC Mutations ────────────────────────────────────

    def add_component(
        self, label: str, bounds: dict, parent_id: str | None = None
    ) -> str:
        comp_id = str(uuid.uuid4())
        payload = {"id": comp_id, "label": label, "bounds": bounds}
        if parent_id:
            payload["parentId"] = str(parent_id)

        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("add_component", payload), self._loop
        )
        return comp_id

    def move_component(self, comp_id: str, x: int, y: int):
        payload = {"id": str(comp_id), "x": x, "y": y}
        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("move_component", payload), self._loop
        )

    def update_component(
        self,
        comp_id: str,
        label: str | None = None,
        bounds: dict | None = None,
        parent_id: str | None = None,
        style: dict | None = None,
        visibility: dict | None = None,
    ):
        payload = {"id": str(comp_id)}
        if label is not None:
            payload["label"] = label
        if bounds is not None:
            payload["bounds"] = bounds
        if parent_id is not None:
            payload["parentId"] = str(parent_id)
        if style is not None:
            payload["style"] = style
        if visibility is not None:
            payload["visibility"] = visibility

        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("update_component", payload), self._loop
        )

    def delete_component(self, comp_id: str):
        payload = {"id": str(comp_id)}
        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("delete_component", payload), self._loop
        )

    def undo(self):
        asyncio.run_coroutine_threadsafe(self._send_json_rpc("undo", {}), self._loop)

    def redo(self):
        asyncio.run_coroutine_threadsafe(self._send_json_rpc("redo", {}), self._loop)

    def update_cut_lines(self, lines: list[int]):
        payload = {"lines": lines}
        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("update_cut_lines", payload), self._loop
        )

    def update_screen_info(self, name: str, description: str):
        payload = {"name": name, "description": description}
        asyncio.run_coroutine_threadsafe(
            self._send_json_rpc("update_screen_info", payload), self._loop
        )

    def get_raw_image_url(self) -> str:
        return f"{self.api_url}/image/raw"

    def get_crop_image_url(self, comp_id: str) -> str:
        return f"{self.api_url}/image/crop/{comp_id}"
