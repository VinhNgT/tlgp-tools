import uuid

from engine.app import app
from engine.state import get_workspace
from fastapi.testclient import TestClient
from models import ImageInfo

client = TestClient(app)


def test_global_exception_handler_component_not_found():
    # Attempt to move a non-existent component
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    comp_id = uuid.uuid4()
    response = client.put(f"/components/{comp_id}/move", json={"x": 100, "y": 200})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_global_exception_handler_parent_not_found():
    # Attempt to add a component with a non-existent parent
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    parent_id = uuid.uuid4()
    response = client.post(
        "/components",
        json={
            "label": "Button",
            "parentId": str(parent_id),
            "bounds": {"x": 10, "y": 20, "w": 100, "h": 50},
        },
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_global_exception_handler_invalid_archive():
    # Upload an invalid zip
    response = client.post(
        "/import",
        files={"file": ("test.zip", b"not a zip file content", "application/zip")},
    )
    assert response.status_code == 400
    assert (
        "zip" in response.json()["detail"].lower()
        or "invalid" in response.json()["detail"].lower()
    )


def test_global_exception_handler_invalid_image():
    # Upload an invalid image
    response = client.post(
        "/import/image",
        files={"file": ("test.png", b"not an image content", "image/png")},
    )
    assert response.status_code == 400
    assert "invalid image format" in response.json()["detail"].lower()


def test_global_exception_handler_invalid_state_export():
    # Export when there is no image in the workspace
    # Clear the workspace state first
    workspace = get_workspace()
    workspace.raw_image_bytes = b""
    workspace.state.image = None

    response = client.get("/export")
    assert response.status_code == 400
    assert "no image" in response.json()["detail"].lower()


def test_global_exception_handler_undo_redo_error():
    # Attempt to undo when there is no history to undo
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    # Reset history
    workspace._history = [workspace.state.model_dump(mode="json")]
    workspace._pointer = 0

    response = client.post("/session/undo")
    assert response.status_code == 400
    assert "cannot undo" in response.json()["detail"].lower()


def test_validation_exception_handler():
    # Attempt to add a component with missing fields (violates payload structure)
    response = client.post(
        "/components",
        json={
            "label": "Button"
            # Missing bounds
        },
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    # Assert validation details describe bounds is missing
    assert any("bounds" in err["loc"] for err in data["detail"])


def test_http_exception_handler():
    # Attempt to access a completely non-existent route
    response = client.get("/non-existent-route-path")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_operation_fails_validation_when_no_image():
    # Clear the workspace image state
    workspace = get_workspace()
    workspace.state.image = None

    # Try to add component without image
    response = client.post(
        "/components",
        json={
            "label": "Button",
            "bounds": {"x": 10, "y": 20, "w": 100, "h": 50},
        },
    )
    assert response.status_code == 400
    assert "no screenshot/image" in response.json()["detail"].lower()

    # Try to move a component without image
    response = client.put(f"/components/{uuid.uuid4()}/move", json={"x": 100, "y": 200})
    assert response.status_code == 400
    assert "no screenshot/image" in response.json()["detail"].lower()


def test_websocket_json_rpc():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    with client.websocket_connect("/ws") as websocket:
        # First message sent on connection is full_sync
        data = websocket.receive_json()
        assert data["type"] == "full_sync"

        # Now send a JSON-RPC request to add a component
        comp_id = str(uuid.uuid4())
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "add_component",
                "params": {
                    "id": comp_id,
                    "label": "JSON-RPC-Test",
                    "bounds": {"x": 10, "y": 20, "w": 100, "h": 50},
                },
                "id": "req-1",
            }
        )

        # Wait for the JSON-RPC response and the broadcast patch
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()

        messages = [msg1, msg2]
        response = next((m for m in messages if "result" in m), None)
        patch = next((m for m in messages if m.get("type") == "patch"), None)

        assert response is not None
        assert response["result"]["status"] == "added"
        assert response["id"] == "req-1"

        assert patch is not None
        assert uuid.UUID(comp_id) in workspace.state.components



