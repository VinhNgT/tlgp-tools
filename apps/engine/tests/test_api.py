import uuid

from engine.app import app
from engine.state import get_workspace
from fastapi.testclient import TestClient

client = TestClient(app)


def test_global_exception_handler_component_not_found():
    # Attempt to move a non-existent component
    comp_id = uuid.uuid4()
    response = client.put(f"/components/{comp_id}/move", json={"x": 100, "y": 200})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_global_exception_handler_parent_not_found():
    # Attempt to add a component with a non-existent parent
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
    # Reset history
    workspace._history = [workspace.state.model_dump(mode="json")]
    workspace._pointer = 0

    response = client.post("/session/undo")
    assert response.status_code == 400
    assert "cannot undo" in response.json()["detail"].lower()
