import asyncio
import json
import threading
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

    def __init__(self, on_state_changed: Callable[[], None]):
        self.state: WorkspaceState | None = None
        self.on_state_changed = on_state_changed
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    logger.info("Connected to Engine WebSocket")
                    async for message in ws:
                        data = json.loads(message)

                        if data.get("type") == "full_sync":
                            self.state = WorkspaceState.model_validate(data["state"])
                            self._trigger_update()

                        elif data.get("type") == "patch":
                            if self.state:
                                old_dict = self.state.model_dump(mode="json")
                                patch = jsonpatch.JsonPatch(data["patch"])
                                new_dict = patch.apply(old_dict)
                                self.state = WorkspaceState.model_validate(new_dict)
                                self._trigger_update()
            except Exception as e:
                logger.error("WS Connection lost, retrying in 2s...", error=str(e))
                await asyncio.sleep(2)

    def _trigger_update(self):
        # Fire callback safely (GUI must handle thread safety if needed)
        if self.on_state_changed:
            self.on_state_changed()

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

    # ── REST API Methods ───────────────────────────────────────────────

    def import_zip(self, zip_path: str):
        with open(zip_path, "rb") as f:
            self._request("POST", f"{API_URL}/import", files={"file": f})

    def import_image(self, image_path: str):
        with open(image_path, "rb") as f:
            self._request("POST", f"{API_URL}/import/image", files={"file": f})

    def add_component(
        self, label: str, bounds: dict, parent_id: str | None = None
    ) -> str:
        payload = {"label": label, "bounds": bounds}
        if parent_id:
            payload["parentId"] = parent_id

        res = self._request("POST", f"{API_URL}/components", json=payload)
        return res.json().get("id")

    def move_component(self, comp_id: str, x: int, y: int):
        self._request(
            "PUT", f"{API_URL}/components/{comp_id}/move", json={"x": x, "y": y}
        )

    def update_component(
        self,
        comp_id: str,
        label: str | None = None,
        bounds: dict | None = None,
        parent_id: str | None = None,
    ):
        payload = {}
        if label is not None:
            payload["label"] = label
        if bounds is not None:
            payload["bounds"] = bounds
        if parent_id is not None:
            payload["parentId"] = parent_id

        self._request("PUT", f"{API_URL}/components/{comp_id}", json=payload)

    def delete_component(self, comp_id: str):
        self._request("DELETE", f"{API_URL}/components/{comp_id}")

    def undo(self):
        self._request("POST", f"{API_URL}/session/undo")

    def redo(self):
        self._request("POST", f"{API_URL}/session/redo")

    def export_zip_data(self) -> requests.Response:
        return self._request("GET", f"{API_URL}/export")

    def get_raw_image_url(self) -> str:
        return f"{API_URL}/image/raw"

    def get_crop_image_url(self, comp_id: str) -> str:
        return f"{API_URL}/image/crop/{comp_id}"
