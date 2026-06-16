import io
import uuid
import zipfile

import pytest

from engine.app import app
from engine.state import get_workspace
from fastapi.testclient import TestClient
from models import Bounds, Component, ImageInfo
from PIL import Image

client = None


@pytest.fixture(autouse=True, scope="module")
def setup_client():
    global client
    if client is None:
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
        "/workspace/import",
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
        "/workspace/import-image",
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

    response = client.get("/workspace/export")
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


def test_image_endpoint_hierarchy():

    # Create a dummy 100x100 transparent image
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    valid_png_bytes = buf.getvalue()

    workspace = get_workspace()
    workspace.raw_image_bytes = valid_png_bytes
    workspace.state.image = ImageInfo(filename="test.png", width=100, height=100)

    # Create a hierarchy:
    # Root Component (parent_id=None)
    #   -> Child Component (Leaf)

    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()

    parent_comp = Component(
        id=parent_id,
        number="1",
        label="Parent",
        bounds=Bounds(x=10, y=10, w=80, h=80),
        childrenIds=[child_id]
    )

    child_comp = Component(
        id=child_id,
        number="1.1",
        label="Child",
        parentId=parent_id,
        bounds=Bounds(x=20, y=20, w=40, h=40),
        childrenIds=[]
    )

    workspace.state.components[parent_id] = parent_comp
    workspace.state.components[child_id] = child_comp
    workspace.state.rootComponents = [parent_id]

    # 1. Test Root
    response = client.get("/images/root")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    # Root with show_children
    response = client.get("/images/root?show_children=true")
    assert response.status_code == 200

    # 2. Test Parent Component
    response = client.get(f"/images/{parent_id}")
    assert response.status_code == 200
    # Parent with show_children
    response = client.get(f"/images/{parent_id}?show_children=true")
    assert response.status_code == 200

    # 3. Test Leaf Component
    response = client.get(f"/images/{child_id}")
    assert response.status_code == 200
    # Leaf with show_children
    response = client.get(f"/images/{child_id}?show_children=true")
    assert response.status_code == 200

    # 4. Test Invalid Format
    response = client.get("/images/invalid-format")
    assert response.status_code == 400
    assert "Invalid component ID format" in response.json()["detail"]

def test_image_endpoint_components():

    # Create a 100x100 dummy image
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    valid_png_bytes = buf.getvalue()

    workspace = get_workspace()
    workspace.raw_image_bytes = valid_png_bytes
    workspace.state.image = ImageInfo(filename="test.png", width=100, height=100)

    # Create parent and leaf components
    parent_id = uuid.uuid4()
    leaf_id = uuid.uuid4()

    parent_comp = Component(
        id=parent_id,
        number="1",
        label="Parent",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        childrenIds=[leaf_id]
    )
    leaf_comp = Component(
        id=leaf_id,
        number="1.1",
        label="Leaf",
        parentId=parent_id,
        bounds=Bounds(x=20, y=20, w=20, h=20)
    )

    workspace.state.components[parent_id] = parent_comp
    workspace.state.components[leaf_id] = leaf_comp
    workspace.state.rootComponents = [parent_id]

    # 1. Test parent image (dimensions should be 50x50)
    res_parent = client.get(f"/images/{parent_id}")
    assert res_parent.status_code == 200

    # We can check the dimensions of the returned image
    returned_img = Image.open(io.BytesIO(res_parent.content))
    assert returned_img.width == 50
    assert returned_img.height == 50

    # 2. Test leaf image (dimensions should be 20x20)
    res_leaf = client.get(f"/images/{leaf_id}")
    assert res_leaf.status_code == 200

    returned_leaf = Image.open(io.BytesIO(res_leaf.content))
    assert returned_leaf.width == 20
    assert returned_leaf.height == 20

    # 3. Test root image with show_children
    res_root_children = client.get("/images/root?show_children=true")
    assert res_root_children.status_code == 200

    res_root_no_children = client.get("/images/root?show_children=false")
    assert res_root_no_children.status_code == 200

    # Verify the image bytes differ, meaning the rendering actually drew the annotations
    assert res_root_children.content != res_root_no_children.content

    # 4. Test parent image with show_children
    res_parent_children = client.get(f"/images/{parent_id}?show_children=true")
    assert res_parent_children.status_code == 200

    # Verify parent image bytes also differ when drawing children
    assert res_parent_children.content != res_parent.content


def test_export_batch():

    # Create a 100x100 dummy image
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    valid_png_bytes = buf.getvalue()

    workspace = get_workspace()
    workspace.raw_image_bytes = valid_png_bytes
    workspace.state.image = ImageInfo(filename="test.png", width=100, height=100)

    comp_id = uuid.uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="Comp",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        childrenIds=[]
    )
    workspace.state.components[comp_id] = comp
    workspace.state.rootComponents = [comp_id]

    payload = {
        "include_state": True,
        "include_root": True,
        "show_root_children": True,
        "components": [
            {"id": str(comp_id), "show_children": False}
        ]
    }

    response = client.post("/workspace/export-batch", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # Verify zip content
    zip_buf = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        namelist = zf.namelist()
        assert "workspace.json" in namelist
        assert "raw.png" in namelist
        assert f"images/{comp_id}.png" in namelist


def test_workspace_readonly_mode():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()
    workspace.state.readOnly = False

    # 1. Enable read-only mode via PUT /workspace/readonly
    response = client.put("/workspace/readonly", json={"read_only": True})
    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert workspace.state.readOnly is True

    # 2. Try to add a component -> should be rejected with 400 Bad Request
    response = client.post(
        "/components",
        json={
            "label": "Button",
            "bounds": {"x": 10, "y": 20, "w": 100, "h": 50},
        },
    )
    assert response.status_code == 400
    assert "read-only" in response.json()["detail"].lower()

    # 3. Disable read-only mode via PUT /workspace/readonly
    response = client.put("/workspace/readonly", json={"read_only": False})
    assert response.status_code == 200
    assert response.json()["read_only"] is False
    assert workspace.state.readOnly is False

    # 4. Try to add a component again -> should succeed
    response = client.post(
        "/components",
        json={
            "label": "Button",
            "bounds": {"x": 10, "y": 20, "w": 100, "h": 50},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "added"


def test_workspace_clear():
    workspace = get_workspace()
    # Setup some state
    comp_uuid = uuid.uuid4()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components = {
        comp_uuid: Component(
            id=comp_uuid,
            number="1",
            label="Dummy",
            bounds=Bounds(x=10, y=10, w=100, h=100)
        )
    }
    workspace.raw_image_bytes = b"fake_bytes"
    workspace.state.cutLines = [150]
    old_session_id = workspace.state.sessionId

    # Call clear workspace API
    response = client.post("/workspace/clear")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["sessionId"] != str(old_session_id)

    # Check that state has been cleared
    assert workspace.state.image is None
    assert len(workspace.state.components) == 0
    assert len(workspace.state.cutLines) == 0
    assert workspace.raw_image_bytes == b""


