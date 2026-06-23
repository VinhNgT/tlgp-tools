"""Tests for annotator.api.routes.WebSocketBroadcaster.

Tests the broadcaster's connect/disconnect lifecycle, sync-to-async
bridging, and thread-safety guarantees — without requiring a live server.
"""

import asyncio
import threading
import uuid

import pytest
from annotator.api.routes import WebSocketBroadcaster
from annotator.models import WorkspaceState


# ── Helpers ────────────────────────────────────────────────────────────


def _make_patch(op: str = "add", path: str = "/components/xyz") -> list[dict]:
    """Create a minimal JSON patch payload."""
    return [{"op": op, "path": path, "value": {"id": str(uuid.uuid4())}}]


def _make_state(revision: int = 1) -> WorkspaceState:
    """Create a minimal WorkspaceState with a given revision."""
    state = WorkspaceState(sessionId=uuid.uuid4())
    state.revision = revision
    return state


# ── Connect / Disconnect ─────────────────────────────────────────────


class TestConnectDisconnect:
    def test_connect_returns_queue(self):
        loop = asyncio.new_event_loop()
        try:
            broadcaster = WebSocketBroadcaster(loop)
            q = broadcaster.connect()
            assert isinstance(q, asyncio.Queue)
        finally:
            loop.close()

    def test_multiple_clients(self):
        loop = asyncio.new_event_loop()
        try:
            broadcaster = WebSocketBroadcaster(loop)
            q1 = broadcaster.connect()
            q2 = broadcaster.connect()
            assert q1 is not q2
        finally:
            loop.close()

    def test_disconnect_removes_client(self):
        loop = asyncio.new_event_loop()
        try:
            broadcaster = WebSocketBroadcaster(loop)
            q = broadcaster.connect()
            broadcaster.disconnect(q)
            # Disconnect a second time should not raise
            broadcaster.disconnect(q)
        finally:
            loop.close()


# ── Broadcast Message Delivery ────────────────────────────────────────


class TestBroadcastDelivery:
    @pytest.mark.anyio()
    async def test_patch_message_delivered(self):
        """A sync broadcast_sync() call should deliver a patch message to connected clients."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q = broadcaster.connect()

        patch = _make_patch()
        state = _make_state(revision=5)
        broadcaster.broadcast_sync(patch, state)

        # Give the event loop a tick to process call_soon_threadsafe
        await asyncio.sleep(0.05)

        assert not q.empty()
        msg = q.get_nowait()
        assert msg["type"] == "patch"
        assert msg["revision"] == 5
        assert msg["patch"] == patch

    @pytest.mark.anyio()
    async def test_full_sync_message(self):
        """A replace-root patch should produce a full_sync message."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q = broadcaster.connect()

        full_replace_patch = [{"op": "replace", "path": "", "value": {"full": True}}]
        state = _make_state()
        broadcaster.broadcast_sync(full_replace_patch, state)

        await asyncio.sleep(0.05)

        msg = q.get_nowait()
        assert msg["type"] == "full_sync"
        assert msg["state"] == {"full": True}

    @pytest.mark.anyio()
    async def test_multiple_clients_receive(self):
        """All connected clients should receive the broadcast."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q1 = broadcaster.connect()
        q2 = broadcaster.connect()

        broadcaster.broadcast_sync(_make_patch(), _make_state())
        await asyncio.sleep(0.05)

        assert not q1.empty()
        assert not q2.empty()

    @pytest.mark.anyio()
    async def test_disconnected_client_does_not_receive(self):
        """A disconnected client's queue should not receive new messages."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q = broadcaster.connect()
        broadcaster.disconnect(q)

        broadcaster.broadcast_sync(_make_patch(), _make_state())
        await asyncio.sleep(0.05)

        assert q.empty()


# ── Thread Safety ─────────────────────────────────────────────────────


class TestBroadcasterThreadSafety:
    @pytest.mark.anyio()
    async def test_broadcast_from_worker_thread(self):
        """broadcast_sync() called from a non-event-loop thread must still deliver."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q = broadcaster.connect()

        def worker():
            broadcaster.broadcast_sync(_make_patch(), _make_state())

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)

        await asyncio.sleep(0.1)
        assert not q.empty()

    @pytest.mark.anyio()
    async def test_concurrent_connect_disconnect(self):
        """Concurrent connect/disconnect must not corrupt the client list."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        queues = []
        lock = threading.Lock()

        def connector():
            for _ in range(20):
                q = broadcaster.connect()
                with lock:
                    queues.append(q)

        def disconnector():
            for _ in range(10):
                with lock:
                    if not queues:
                        continue
                    q = queues.pop(0)
                broadcaster.disconnect(q)

        threads = [
            threading.Thread(target=connector),
            threading.Thread(target=disconnector),
            threading.Thread(target=connector),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # After all threads complete, broadcast should not crash
        broadcaster.broadcast_sync(_make_patch(), _make_state())
        await asyncio.sleep(0.05)

    @pytest.mark.anyio()
    async def test_queue_full_does_not_crash(self):
        """If a client's queue is full, broadcast should silently drop the message."""
        loop = asyncio.get_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        q = broadcaster.connect()

        # Fill the queue to capacity (64)
        for _ in range(64):
            broadcaster.broadcast_sync(_make_patch(), _make_state())
            await asyncio.sleep(0.01)

        # One more should not raise
        broadcaster.broadcast_sync(_make_patch(), _make_state())
        await asyncio.sleep(0.05)

        assert q.qsize() == 64  # Queue stayed at max capacity


# ── Closed Loop Resilience ────────────────────────────────────────────


class TestClosedLoopResilience:
    def test_broadcast_after_loop_closed(self):
        """Broadcasting after the event loop is closed must not raise."""
        loop = asyncio.new_event_loop()
        broadcaster = WebSocketBroadcaster(loop)
        broadcaster.connect()
        loop.close()

        # Should silently return — the is_closed() check prevents the call
        broadcaster.broadcast_sync(_make_patch(), _make_state())
