import asyncio

import pytest
from engine.api import ClientConnection, websocket_endpoint
from engine.state import WorkspaceManager
from fastapi import WebSocketDisconnect


@pytest.fixture
def anyio_backend():
    return "asyncio"


class MockWebSocket:
    def __init__(self, texts_to_receive=None, raise_disconnect=False):
        self.texts_to_receive = texts_to_receive or []
        self.sent_jsons = []
        self.accepted = False
        self.raise_disconnect = raise_disconnect
        self._receive_index = 0

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent_jsons.append(data)

    async def receive_text(self) -> str:
        if self.raise_disconnect:
            raise WebSocketDisconnect()
        if self._receive_index < len(self.texts_to_receive):
            val = self.texts_to_receive[self._receive_index]
            self._receive_index += 1
            return val
        # Wait forever to simulate idling connection
        await asyncio.sleep(10)
        raise WebSocketDisconnect()


@pytest.mark.anyio
async def test_client_connection_queue_drop():
    ws = MockWebSocket()
    # Create a queue of size 1 and fill it
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait({"type": "initial"})

    conn = ClientConnection(ws, queue)
    try:
        # Putting another message now should be dropped silently by put_nowait
        conn.send_msg({"type": "dropped"})
        assert queue.full()
        assert queue.qsize() == 1
    finally:
        conn.cancel()


@pytest.mark.anyio
async def test_workspace_manager_broadcast_patch_queue_drop():
    manager = WorkspaceManager()
    # Connect a listener queue of size 1
    queue = asyncio.Queue(maxsize=1)
    manager._listeners.append(queue)

    # Initial state is put during connect normally, but we put it manually to fill it
    queue.put_nowait({"type": "initial"})

    # Broadcast should swallow QueueFull silently
    manager.broadcast_patch([{"op": "replace", "path": "/revision", "value": 1}])
    assert queue.full()


@pytest.mark.anyio
async def test_websocket_endpoint_disconnect_cleanup():
    manager = WorkspaceManager()
    # Mock WebSocket that immediately disconnects on receive_text
    ws = MockWebSocket(raise_disconnect=True)

    # Invoke websocket_endpoint and ensure it exits cleanly
    await websocket_endpoint(ws, manager)

    # Verify connection was disconnected and queue removed from listeners list
    assert len(manager._listeners) == 0
