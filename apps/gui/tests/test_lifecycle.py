import threading
import time

from gui.api_client import EngineClient


def test_engine_client_lifecycle():
    initial_threads = threading.active_count()

    client = EngineClient(
        on_state_changed=lambda: None,
        on_error=None,
        ws_url="ws://127.0.0.1:9999/ws",
    )

    # Verify no thread is spawned on initialization
    assert client._thread is None
    assert threading.active_count() == initial_threads

    # Start the client background connection task
    client.start()

    # The background thread should be active
    assert client._thread is not None
    assert client._thread.is_alive()
    assert threading.active_count() > initial_threads

    # Allow the loop to perform connection attempts briefly
    time.sleep(0.1)

    # Stop the client
    client.stop()

    # Thread and loop should be stopped and cleaned up
    assert client._thread is None
    assert threading.active_count() == initial_threads
