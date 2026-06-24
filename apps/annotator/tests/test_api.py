"""Tests for annotator.api (FastAPI routes and exception handling).

Uses httpx.ASGITransport for testing without spawning a server.
"""

import io
import uuid

import httpx
import pytest
from annotator.api.app import create_app
from annotator.models import Bounds
from annotator.workspace import WorkspaceManager
from PIL import Image


def _create_test_image(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def workspace():
    ws = WorkspaceManager()
    ws.import_image(_create_test_image())
    return ws


@pytest.fixture()
def app(workspace):
    yield create_app(workspace)


@pytest.fixture()
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── State Routes ───────────────────────────────────────────────────────


class TestStateRoutes:
    @pytest.mark.anyio()
    async def test_get_state(self, client, workspace):
        resp = await client.get("/workspace/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "workspaceId" in data
        assert "components" in data

    @pytest.mark.anyio()
    async def test_set_readonly(self, client, workspace):
        resp = await client.put("/workspace/readonly", json={"read_only": True})
        assert resp.status_code == 200
        assert workspace.state.readOnly is True

    @pytest.mark.anyio()
    async def test_clear_workspace(self, client, workspace):
        resp = await client.post("/workspace/clear")
        assert resp.status_code == 200
        assert workspace.state.image is None


# ── Component Routes ──────────────────────────────────────────────────


class TestComponentRoutes:
    @pytest.mark.anyio()
    async def test_add_component(self, client, workspace):
        comp_id = str(uuid.uuid4())
        resp = await client.post(
            "/components",
            json={
                "id": comp_id,
                "label": "Button",
                "bounds": {"x": 10, "y": 10, "w": 50, "h": 30},
            },
        )
        assert resp.status_code == 200
        assert uuid.UUID(comp_id) in workspace.state.components

    @pytest.mark.anyio()
    async def test_delete_component(self, client, workspace):
        comp_id = uuid.uuid4()
        workspace.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))
        resp = await client.delete(f"/components/{comp_id}")
        assert resp.status_code == 200
        assert comp_id not in workspace.state.components

    @pytest.mark.anyio()
    async def test_delete_nonexistent_returns_404(self, client):
        fake_id = uuid.uuid4()
        resp = await client.delete(f"/components/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.anyio()
    async def test_move_component(self, client, workspace):
        comp_id = uuid.uuid4()
        workspace.add_component(comp_id, "Box", Bounds(x=10, y=10, w=50, h=50))
        resp = await client.put(
            f"/components/{comp_id}/move", json={"x": 100, "y": 100}
        )
        assert resp.status_code == 200
        assert workspace.state.components[comp_id].bounds.x == 100


# ── Undo/Redo Routes ──────────────────────────────────────────────────


class TestUndoRedoRoutes:
    @pytest.mark.anyio()
    async def test_undo_redo_cycle(self, client, workspace):
        comp_id = uuid.uuid4()
        workspace.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))

        resp = await client.post("/workspace/undo")
        assert resp.status_code == 200
        assert comp_id not in workspace.state.components

        resp = await client.post("/workspace/redo")
        assert resp.status_code == 200
        assert comp_id in workspace.state.components

    @pytest.mark.anyio()
    async def test_undo_at_beginning_returns_409(self, client):
        resp = await client.post("/workspace/undo")
        assert resp.status_code == 409


# ── Import/Export Routes ──────────────────────────────────────────────


class TestImportExportRoutes:
    @pytest.mark.anyio()
    async def test_import_image(self, client, workspace):
        old_workspace_id = workspace.state.workspaceId
        img_bytes = _create_test_image(320, 240)
        resp = await client.post(
            "/workspace/import-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert resp.status_code == 200
        assert workspace.state.image.width == 320
        assert workspace.state.workspaceId != old_workspace_id

    @pytest.mark.anyio()
    async def test_export_zip(self, client, workspace):
        resp = await client.get("/workspace/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    @pytest.mark.anyio()
    async def test_import_zip_roundtrip(self, client, workspace):
        comp_id = uuid.uuid4()
        workspace.add_component(comp_id, "Box", Bounds(x=10, y=10, w=50, h=50))
        export_resp = await client.get("/workspace/export")
        assert export_resp.status_code == 200

        # Import into a fresh workspace
        resp = await client.post(
            "/workspace/import",
            files={"file": ("export.zip", export_resp.content, "application/zip")},
        )
        assert resp.status_code == 200
        assert comp_id in workspace.state.components


# ── Image Route ───────────────────────────────────────────────────────


class TestImageRoute:
    @pytest.mark.anyio()
    async def test_get_root_image(self, client):
        resp = await client.get("/images/root")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    @pytest.mark.anyio()
    async def test_get_component_image(self, client, workspace):
        comp_id = uuid.uuid4()
        workspace.add_component(comp_id, "Box", Bounds(x=10, y=10, w=50, h=50))
        resp = await client.get(f"/images/{comp_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    @pytest.mark.anyio()
    async def test_get_nonexistent_component_image_returns_404(self, client):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/images/{fake_id}")
        assert resp.status_code == 404


# ── Exception Handler ─────────────────────────────────────────────────


class TestExceptionHandler:
    @pytest.mark.anyio()
    async def test_readonly_returns_403(self, client, workspace):
        workspace.mutate(lambda s: setattr(s, "readOnly", True), force=True)
        resp = await client.post(
            "/components",
            json={
                "label": "X",
                "bounds": {"x": 0, "y": 0, "w": 10, "h": 10},
            },
        )
        assert resp.status_code == 403
        assert "detail" in resp.json()
