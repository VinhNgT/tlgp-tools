"""Shared test fixtures for the annotator test suite."""

import io
import os
import uuid

import httpx
import pytest
from annotator.api.app import create_app
from annotator.models import Bounds
from annotator.workspace import WorkspaceManager
from PIL import Image
from PySide6.QtWidgets import QApplication

# Configure Qt to run headlessly to avoid launching graphical windows
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    """A session-wide QApplication instance configured for headless execution."""
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def create_test_image(width: int = 800, height: int = 600) -> bytes:
    """Create a minimal PNG image in memory and return its bytes."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def workspace_with_image(width: int = 800, height: int = 600) -> WorkspaceManager:
    """Create a WorkspaceManager with an image already loaded."""
    ws = WorkspaceManager()
    ws.import_image(create_test_image(width, height))
    return ws


def add_test_component(
    ws: WorkspaceManager,
    x: int = 0,
    y: int = 0,
    w: int = 50,
    h: int = 50,
    label: str = "Component",
    parent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Add a component to the workspace and return its ID."""
    comp_id = uuid.uuid4()
    ws.add_component(comp_id, label, Bounds(x=x, y=y, w=w, h=h), parent_id=parent_id)
    return comp_id


@pytest.fixture()
def workspace():
    """A WorkspaceManager with a test image loaded."""
    return workspace_with_image()


@pytest.fixture()
def app(workspace):
    """A FastAPI app wired to a test workspace."""
    yield create_app(workspace)


@pytest.fixture()
async def client(app):
    """An async httpx client for testing FastAPI routes without a server."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
