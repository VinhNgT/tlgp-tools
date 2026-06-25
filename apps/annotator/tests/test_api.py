"""Tests for annotator.api (FastAPI routes and exception handling).

Uses httpx.ASGITransport for testing without spawning a server.
"""

import io
import uuid
import zipfile

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

# ── Import/Export Routes ──────────────────────────────────────────────


class TestImportExportRoutes:
    @pytest.mark.anyio()
    async def test_export_zip(self, client, workspace):
        resp = await client.get("/workspace/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    @pytest.mark.anyio()
    async def test_export_images_annotated(self, client, workspace):
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        workspace.add_component(parent_id, "Parent", Bounds(x=10, y=10, w=100, h=100))
        workspace.add_component(child_id, "Child", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id)

        resp = await client.get("/workspace/export-images?mode=annotated")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.headers["content-disposition"] == "attachment; filename=screenshot_annotated.zip"

        with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
            names = zf.namelist()
            assert any("Parent" in name for name in names)
            assert not any("Child" in name for name in names)
            assert all(not name.startswith("annotated/") for name in names)

    @pytest.mark.anyio()
    async def test_export_images_raw(self, client, workspace):
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        workspace.add_component(parent_id, "Parent", Bounds(x=10, y=10, w=100, h=100))
        workspace.add_component(child_id, "Child", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id)

        resp = await client.get("/workspace/export-images?mode=raw")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.headers["content-disposition"] == "attachment; filename=screenshot_raw.zip"

        with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
            names = zf.namelist()
            assert any("Parent" in name for name in names)
            assert any("Child" in name for name in names)
            assert all(not name.startswith("raw/") for name in names)

    @pytest.mark.anyio()
    async def test_export_images_both(self, client, workspace):
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        workspace.add_component(parent_id, "Parent", Bounds(x=10, y=10, w=100, h=100))
        workspace.add_component(child_id, "Child", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id)

        resp = await client.get("/workspace/export-images?mode=both")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.headers["content-disposition"] == "attachment; filename=screenshot_both.zip"

        with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
            names = zf.namelist()
            assert any(name.startswith("annotated/") and "Parent" in name for name in names)
            assert not any(name.startswith("annotated/") and "Child" in name for name in names)
            assert any(name.startswith("raw/") and "Parent" in name for name in names)
            assert any(name.startswith("raw/") and "Child" in name for name in names)






