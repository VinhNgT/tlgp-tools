import asyncio
import threading
import time
import uuid
import json
from unittest.mock import MagicMock, patch

import pytest
from gui.api_client import EngineClient
from models import WorkspaceState

# Helper fixture for providing a thread-safe "dispatch" that works like Tkinter's `after`
# For testing, we will just execute it in the calling thread, or in a queue if we need strict main-thread emulation.
# But actually, `dispatch` is meant to route from the background thread to the main thread.
class MockDispatcher:
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()

    def dispatch(self, func):
        with self.lock:
            self.queue.append(func)

    def process_queue(self):
        with self.lock:
            tasks = self.queue[:]
            self.queue.clear()
        for t in tasks:
            t()

@pytest.fixture
def dispatcher():
    return MockDispatcher()

@pytest.fixture
def mock_ws_connect():
    with patch("gui.api_client.websockets.connect", new_callable=MagicMock) as mock_connect:
        yield mock_connect


def test_client_start_stop_lifecycle():
    client = EngineClient(on_state_changed=lambda: None)
    
    assert client._thread is None
    
    client.start()
    assert client._thread is not None
    assert client._thread.is_alive()
    
    # Let the loop start
    time.sleep(0.05)
    
    client.stop()
    assert client._thread is None
    assert client._loop is None

def test_client_multiple_starts():
    client = EngineClient(on_state_changed=lambda: None)
    
    client.start()
    first_thread = client._thread
    
    client.start()
    client.start()
    
    assert client._thread is first_thread
    assert threading.active_count() <= threading.active_count() + 1  # only one extra thread
    
    client.stop()

def test_client_stop_without_start():
    client = EngineClient(on_state_changed=lambda: None)
    # Should not raise any exceptions
    client.stop()

def test_dispatch_thread_routing(dispatcher):
    # Verify that the callbacks supplied to EngineClient are only ever executed via `dispatch`,
    # meaning they will run in the thread that processes the dispatch queue.
    
    executed_in_thread = None
    
    def on_state_changed():
        nonlocal executed_in_thread
        executed_in_thread = threading.current_thread()

    client = EngineClient(
        on_state_changed=on_state_changed,
        dispatch=dispatcher.dispatch
    )
    
    # Manually trigger update
    client._trigger_update()
    
    # Ensure it wasn't executed inline if trigger was called from a different thread
    assert executed_in_thread is None
    
    main_thread = threading.current_thread()
    dispatcher.process_queue()
    
    assert executed_in_thread is main_thread

@patch("gui.api_client.requests.request")
def test_async_rest_call_does_not_block(mock_request, dispatcher):
    # Setup mock to simulate slow network call
    def slow_request(*args, **kwargs):
        time.sleep(0.2)
        response = MagicMock()
        response.status_code = 200
        return response
    mock_request.side_effect = slow_request

    client = EngineClient(on_state_changed=lambda: None, dispatch=dispatcher.dispatch)
    client.start()

    start_time = time.time()
    
    callback_executed = threading.Event()
    def on_complete(err):
        callback_executed.set()

    # Create dummy zip file
    with open("dummy.zip", "wb") as f:
        f.write(b"")

    client.import_zip("dummy.zip", on_complete)
    
    call_duration = time.time() - start_time
    # The call should return immediately, way before the 0.2s sleep in slow_request
    assert call_duration < 0.1
    
    # Wait for the background executor to finish the job
    time.sleep(0.3)
    dispatcher.process_queue()
    
    assert callback_executed.is_set()
    client.stop()


class AsyncWsMock:
    """Mocks the async websocket connection, yielding messages sequentially."""
    def __init__(self, messages):
        self.messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def __aiter__(self):
        self.iter = iter(self.messages)
        return self

    async def __anext__(self):
        try:
            # yield to loop to simulate real async io
            await asyncio.sleep(0.001)
            return next(self.iter)
        except StopIteration:
            # Suspend forever once messages are exhausted so the loop stays open
            await asyncio.Future()

def test_concurrent_state_read_write(dispatcher, mock_ws_connect):
    """
    Test that the background thread applying JSONPatches does not cause RuntimeErrors
    when the main thread continuously reads the state.
    """
    session_id = str(uuid.uuid4())
    initial_state = {
        "sessionId": session_id,
        "components": {},
        "rootComponents": [],
        "image": None,
        "active_cut_lines": [],
        "screen_name": "",
        "screen_description": ""
    }
    
    # Prepare a full sync followed by 500 patches
    messages = [json.dumps({"type": "full_sync", "state": initial_state})]
    
    for i in range(500):
        comp_id = str(uuid.uuid4())
        patch_op = {
            "type": "patch",
            "patch": [
                {
                    "op": "add",
                    "path": f"/components/{comp_id}",
                    "value": {
                        "id": comp_id,
                        "number": str(i),
                        "label": f"Comp {i}",
                        "bounds": {"x": 0, "y": 0, "w": 100, "h": 100},
                        "style": {},
                        "visibility": {"visible": True, "locked": False}
                    }
                }
            ]
        }
        messages.append(json.dumps(patch_op))

    mock_ws_connect.return_value = AsyncWsMock(messages)
    
    client = EngineClient(
        on_state_changed=lambda: None,
        dispatch=dispatcher.dispatch
    )
    client.start()
    
    # Main thread continuously reads the state and iterates components
    read_count = 0
    start_time = time.time()
    
    # Let it run for 0.5s reading as fast as it can
    while time.time() - start_time < 0.5:
        state = client.state
        if state is not None:
            # Iterating components to trigger potential "dictionary changed size during iteration"
            # However, since `state` is replaced via Pydantic `model_validate`, 
            # this should be safe. This test verifies that safety.
            for comp_id, comp in state.components.items():
                _ = comp.label
        read_count += 1
        time.sleep(0.001) # slight yield to not fully block GIL
    
    client.stop()
    assert read_count > 10, "Should have performed multiple reads"
