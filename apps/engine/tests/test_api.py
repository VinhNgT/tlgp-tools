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
    assert response.status_code == 422
    assert "no screenshot/image" in response.json()["detail"].lower()

    # Try to move a component without image
    response = client.put(f"/components/{uuid.uuid4()}/move", json={"x": 100, "y": 200})
    assert response.status_code == 422
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


def test_auto_numbering_layout_sort():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create components out of reading order to verify auto-numbering corrects them
    # Component A: Row 1, Col 2 (x=100, y=100, w=50, h=50)
    comp_a_id = uuid.uuid4()
    # Component B: Row 1, Col 3 (x=200, y=105, w=50, h=50)
    comp_b_id = uuid.uuid4()
    # Component C: Row 1, Col 1 (x=10, y=102, w=50, h=50)
    comp_c_id = uuid.uuid4()
    # Component D: Row 2, Col 1 (x=50, y=200, w=50, h=50)
    comp_d_id = uuid.uuid4()

    # Add components via client REST API (which calls recalculate_tree)
    client.post(
        "/components",
        json={
            "id": str(comp_a_id),
            "label": "Box A",
            "bounds": {"x": 100, "y": 100, "w": 50, "h": 50},
        },
    )
    client.post(
        "/components",
        json={
            "id": str(comp_b_id),
            "label": "Box B",
            "bounds": {"x": 200, "y": 105, "w": 50, "h": 50},
        },
    )
    client.post(
        "/components",
        json={
            "id": str(comp_c_id),
            "label": "Box C",
            "bounds": {"x": 10, "y": 102, "w": 50, "h": 50},
        },
    )
    client.post(
        "/components",
        json={
            "id": str(comp_d_id),
            "label": "Box D",
            "bounds": {"x": 50, "y": 200, "w": 50, "h": 50},
        },
    )

    # Verify auto-numbering order in Workspace State:
    # 1. Box C (number '1')
    # 2. Box A (number '2')
    # 3. Box B (number '3')
    # 4. Box D (number '4')
    assert workspace.state.components[comp_c_id].number == "1"
    assert workspace.state.components[comp_a_id].number == "2"
    assert workspace.state.components[comp_b_id].number == "3"
    assert workspace.state.components[comp_d_id].number == "4"

    # Verify rootComponents order
    assert workspace.state.rootComponents == [
        comp_c_id,
        comp_a_id,
        comp_b_id,
        comp_d_id,
    ]


def test_boundary_violation():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create a parent box (x=100, y=100, w=200, h=200)
    parent_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(parent_id),
            "label": "Parent Box",
            "bounds": {"x": 100, "y": 100, "w": 200, "h": 200},
        },
    )

    # Attempt to add a child box exceeding parent bounds (e.g. x=50, y=120)
    child_id = uuid.uuid4()
    response = client.post(
        "/components",
        json={
            "id": str(child_id),
            "label": "Out of Bounds Child",
            "parentId": str(parent_id),
            "bounds": {"x": 50, "y": 120, "w": 100, "h": 50},
        },
    )

    assert response.status_code == 400
    assert "bounds violate parent boundaries" in response.json()["detail"].lower()
    assert response.json()["details"]["component_id"] == str(child_id)
    assert response.json()["details"]["parent_id"] == str(parent_id)

    # Attempt to move parent so child is out of bounds (parent has no children here yet,
    # let's add a valid child first)
    valid_child_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(valid_child_id),
            "label": "Valid Child",
            "parentId": str(parent_id),
            "bounds": {"x": 120, "y": 120, "w": 50, "h": 50},
        },
    )

    # Move parent so the valid child goes out of bounds: parent moves from x=100 to x=150,
    # now parent bounds are x=150..350, but child is still at x=120 (which is out of bounds!)
    response = client.put(f"/components/{parent_id}/move", json={"x": 150, "y": 100})
    assert response.status_code == 400
    assert "bounds violate parent boundaries" in response.json()["detail"].lower()


def test_child_numbering_single_digit():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create root component (Parent Box)
    parent_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(parent_id),
            "label": "Parent Box",
            "bounds": {"x": 100, "y": 100, "w": 300, "h": 300},
        },
    )

    # Create first child component inside Parent Box
    child1_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(child1_id),
            "label": "Child Box 1",
            "parentId": str(parent_id),
            "bounds": {"x": 110, "y": 110, "w": 100, "h": 100},
        },
    )

    # Create second child component inside Parent Box
    child2_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(child2_id),
            "label": "Child Box 2",
            "parentId": str(parent_id),
            "bounds": {"x": 220, "y": 110, "w": 50, "h": 50},
        },
    )

    # Create grandchild component inside Child Box 1
    grandchild_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(grandchild_id),
            "label": "Grandchild Box",
            "parentId": str(child1_id),
            "bounds": {"x": 120, "y": 120, "w": 50, "h": 50},
        },
    )

    # Verify component numbers are all single-digit relative numbers
    assert workspace.state.components[parent_id].number == "1"
    assert workspace.state.components[child1_id].number == "1"
    assert workspace.state.components[child2_id].number == "2"
    assert workspace.state.components[grandchild_id].number == "1"


def test_move_parent_shifts_descendants():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create parent box
    parent_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(parent_id),
            "label": "Parent Box",
            "bounds": {"x": 100, "y": 100, "w": 200, "h": 200},
        },
    )

    # Create child box nested inside parent
    child_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(child_id),
            "label": "Child Box",
            "parentId": str(parent_id),
            "bounds": {"x": 120, "y": 120, "w": 50, "h": 50},
        },
    )

    # Move parent by dx=+50, dy=-30
    response = client.put(f"/components/{parent_id}/move", json={"x": 150, "y": 70})
    assert response.status_code == 200

    # Assert parent bounds updated
    assert workspace.state.components[parent_id].bounds.x == 150
    assert workspace.state.components[parent_id].bounds.y == 70

    # Assert child bounds shifted by same dx=+50, dy=-30
    assert workspace.state.components[child_id].bounds.x == 170
    assert workspace.state.components[child_id].bounds.y == 90


def test_resize_parent_violates_children():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create parent box
    parent_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(parent_id),
            "label": "Parent Box",
            "bounds": {"x": 100, "y": 100, "w": 200, "h": 200},
        },
    )

    # Create child box nested inside parent
    child_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(child_id),
            "label": "Child Box",
            "parentId": str(parent_id),
            "bounds": {"x": 150, "y": 150, "w": 50, "h": 50},
        },
    )

    # Attempt to resize parent to be too small to fit the child
    response = client.put(
        f"/components/{parent_id}",
        json={"bounds": {"x": 100, "y": 100, "w": 40, "h": 40}},
    )

    assert response.status_code == 400
    assert "bounds violate parent boundaries" in response.json()["detail"].lower()


def test_resize_parent_keeps_children_absolute():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Create parent box
    parent_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(parent_id),
            "label": "Parent Box",
            "bounds": {"x": 100, "y": 100, "w": 200, "h": 200},
        },
    )

    # Create child box nested inside parent
    child_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(child_id),
            "label": "Child Box",
            "parentId": str(parent_id),
            "bounds": {"x": 120, "y": 120, "w": 50, "h": 50},
        },
    )

    # Resize parent by shifting its top-left corner outwards to expand bounds
    response = client.put(
        f"/components/{parent_id}",
        json={"bounds": {"x": 90, "y": 80, "w": 220, "h": 230}},
    )
    assert response.status_code == 200

    # Assert parent bounds updated
    assert workspace.state.components[parent_id].bounds.x == 90
    assert workspace.state.components[parent_id].bounds.y == 80

    # Assert child bounds remained at original absolute position
    assert workspace.state.components[child_id].bounds.x == 120
    assert workspace.state.components[child_id].bounds.y == 120


def test_update_cut_lines_and_history():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()
    workspace.state.cutLines.clear()

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # Consume full_sync

        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_cut_lines",
                "params": {"lines": [200, 100]},
                "id": "cuts-1",
            }
        )

        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        msgs = [msg1, msg2]
        resp = next((m for m in msgs if "result" in m), None)
        assert resp is not None
        assert resp["result"]["status"] == "updated_cuts"

        # Verify cutLines are updated and sorted
        assert workspace.state.cutLines == [100, 200]

        # Verify undo works for cut lines
        websocket.send_json(
            {"jsonrpc": "2.0", "method": "undo", "params": {}, "id": "undo-1"}
        )
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        msgs = [msg1, msg2]
        resp = next((m for m in msgs if "result" in m), None)
        assert resp is not None
        assert resp["result"]["status"] == "undone"
        assert workspace.state.cutLines == []

        # Verify redo works
        websocket.send_json(
            {"jsonrpc": "2.0", "method": "redo", "params": {}, "id": "redo-1"}
        )
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        msgs = [msg1, msg2]
        resp = next((m for m in msgs if "result" in m), None)
        assert resp is not None
        assert resp["result"]["status"] == "redone"
        assert workspace.state.cutLines == [100, 200]


def test_update_cut_lines_validation():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()
    workspace.state.cutLines.clear()

    # Add a component at Y: 150 to 250
    comp_id = uuid.uuid4()
    client.post(
        "/components",
        json={
            "id": str(comp_id),
            "label": "Test Component",
            "bounds": {"x": 100, "y": 150, "w": 100, "h": 100},
        },
    )

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # full_sync

        # Attempt to add cut line at Y=200 (intersects component bounds [150, 250])
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_cut_lines",
                "params": {"lines": [200]},
                "id": "cuts-invalid",
            }
        )

        resp = websocket.receive_json()
        assert "error" in resp
        assert "intersects component" in resp["error"]["message"]

        # Consume the follow-up full_sync message sent to revert state
        sync_msg = websocket.receive_json()
        assert sync_msg.get("type") == "full_sync"

        assert workspace.state.cutLines == []

        # Cut line at Y=100 (non-intersecting) is valid
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_cut_lines",
                "params": {"lines": [100]},
                "id": "cuts-valid",
            }
        )
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        msgs = [msg1, msg2]
        resp2 = next((m for m in msgs if "result" in m), None)
        assert resp2 is not None
        assert resp2["result"]["status"] == "updated_cuts"
        assert workspace.state.cutLines == [100]


def test_component_bounds_minimum_dimensions_validation():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Attempt to add a component with invalid width (w=3 < 4)
    response = client.post(
        "/components",
        json={
            "label": "Invalid Width Component",
            "bounds": {"x": 10, "y": 20, "w": 3, "h": 10},
        },
    )
    assert response.status_code == 422

    # Attempt to add a component with invalid height (h=2 < 4)
    response = client.post(
        "/components",
        json={
            "label": "Invalid Height Component",
            "bounds": {"x": 10, "y": 20, "w": 10, "h": 2},
        },
    )
    assert response.status_code == 422


def test_websocket_invalid_bounds_sends_full_sync_and_error():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # Consume initial full_sync

        # Send an invalid add_component request (w=2 < 4)
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "add_component",
                "params": {
                    "label": "Invalid",
                    "bounds": {"x": 10, "y": 20, "w": 2, "h": 10},
                },
                "id": "invalid-add",
            }
        )

        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()

        # Find error message and full_sync message
        error_resp = msg1 if "error" in msg1 else msg2
        sync_resp = msg2 if "error" in msg1 else msg1

        assert "error" in error_resp
        assert sync_resp.get("type") == "full_sync"


def test_update_screen_info():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.screen.name = ""
    workspace.state.screen.description = ""

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # Consume initial full_sync

        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_screen_info",
                "params": {
                    "name": "My New Screen",
                    "description": "Functional description of screen",
                },
                "id": "update-screen-info-id",
            }
        )

        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        messages = [msg1, msg2]
        response = next((m for m in messages if "result" in m), None)
        patch = next((m for m in messages if m.get("type") == "patch"), None)

        assert response is not None
        assert response.get("id") == "update-screen-info-id"
        assert response.get("result") == {"status": "updated_screen_info"}
        assert patch is not None

        # Verify mutation occurred
        assert workspace.state.screen.name == "My New Screen"
        assert workspace.state.screen.description == "Functional description of screen"


def test_update_component_visibility():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # Consume initial full_sync

        # 1. Add a component first
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "add_component",
                "params": {
                    "label": "My Component",
                    "bounds": {"x": 10, "y": 20, "w": 100, "h": 200},
                },
                "id": "add-comp-id",
            }
        )
        msg1 = websocket.receive_json()
        msg2 = websocket.receive_json()
        messages1 = [msg1, msg2]
        resp1 = next((m for m in messages1 if "result" in m), None)
        patch1 = next((m for m in messages1 if m.get("type") == "patch"), None)
        assert resp1 is not None
        assert patch1 is not None

        comp_id = list(workspace.state.components.keys())[0]

        # 2. Update visibility (visible=False, locked=True)
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_component",
                "params": {
                    "id": str(comp_id),
                    "visibility": {"visible": False, "locked": True},
                },
                "id": "update-vis-id",
            }
        )
        msg3 = websocket.receive_json()
        msg4 = websocket.receive_json()
        messages2 = [msg3, msg4]
        resp2 = next((m for m in messages2 if "result" in m), None)
        patch2 = next((m for m in messages2 if m.get("type") == "patch"), None)

        assert resp2 is not None
        assert resp2.get("id") == "update-vis-id"
        assert patch2 is not None

        comp = workspace.state.components[comp_id]
        assert comp.visibility.visible is False
        assert comp.visibility.locked is True


def test_visibility_toggling_updates_numbering():
    workspace = get_workspace()
    workspace.state.image = ImageInfo(filename="test.png", width=800, height=600)
    workspace.state.components.clear()
    workspace.state.rootComponents.clear()

    # Add three siblings in sorted visual positions
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # Consume initial full_sync

        comp_ids = []
        for i, y in enumerate([10, 20, 30]):
            websocket.send_json(
                {
                    "jsonrpc": "2.0",
                    "method": "add_component",
                    "params": {
                        "label": f"Comp {i + 1}",
                        "bounds": {"x": 10, "y": y, "w": 50, "h": 50},
                    },
                    "id": f"add-{i}",
                }
            )
            websocket.receive_json()
            websocket.receive_json()
            comp_ids.append(list(workspace.state.components.keys())[-1])

        # Verify initial numbering
        assert workspace.state.components[comp_ids[0]].number == "1"
        assert workspace.state.components[comp_ids[1]].number == "2"
        assert workspace.state.components[comp_ids[2]].number == "3"

        # Hide Comp 2 (index 1)
        websocket.send_json(
            {
                "jsonrpc": "2.0",
                "method": "update_component",
                "params": {
                    "id": str(comp_ids[1]),
                    "visibility": {"visible": False, "locked": False},
                },
                "id": "hide-comp-2",
            }
        )
        websocket.receive_json()
        websocket.receive_json()

        # Verify numbering updated:
        # Comp 1 (visible) -> number "1"
        # Comp 2 (hidden)  -> number ""
        # Comp 3 (visible) -> number "2"
        assert workspace.state.components[comp_ids[0]].number == "1"
        assert workspace.state.components[comp_ids[1]].number == ""
        assert workspace.state.components[comp_ids[2]].number == "2"
