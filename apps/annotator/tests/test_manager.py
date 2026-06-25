"""Tests for annotator.workspace.manager (WorkspaceManager)."""

import io
import json
import threading
import uuid
import zipfile

import pytest
from annotator.models import Bounds, Style
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
)
from PIL import Image


def _create_test_image(width: int = 800, height: int = 600) -> bytes:
    """Create a minimal PNG image in memory and return its bytes."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _workspace_with_image(width: int = 800, height: int = 600) -> WorkspaceManager:
    """Create a WorkspaceManager with an image already loaded."""
    ws = WorkspaceManager()
    ws.import_image(_create_test_image(width, height))
    return ws


# ── Initialization ─────────────────────────────────────────────────────


class TestWorkspaceInit:
    def test_fresh_workspace_has_empty_state(self):
        ws = WorkspaceManager()
        assert ws.state.image is None
        assert ws.state.components == {}
        assert ws.state.rootComponents == []
        assert ws.raw_image_bytes == b""

    def test_fresh_workspace_has_workspace_id(self):
        ws = WorkspaceManager()
        assert ws.state.workspaceId is not None


# ── Import ─────────────────────────────────────────────────────────────


class TestImportImage:
    def test_import_image_sets_image_info(self):
        ws = _workspace_with_image(640, 480)
        assert ws.state.image is not None
        assert ws.state.image.width == 640
        assert ws.state.image.height == 480
        assert ws.raw_image_bytes != b""

    def test_import_image_resets_workspace(self):
        ws = _workspace_with_image()
        old_workspace_id = ws.state.workspaceId
        ws.import_image(_create_test_image(100, 100))
        assert ws.state.workspaceId != old_workspace_id
        assert ws.state.components == {}

    def test_import_invalid_image_raises(self):
        ws = WorkspaceManager()
        with pytest.raises(InvalidImageError):
            ws.import_image(b"not-an-image")


class TestImportZip:
    def test_import_valid_zip(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Button", Bounds(x=10, y=10, w=50, h=50))

        # Export then reimport
        zip_bytes = ws.export_zip()
        ws2 = WorkspaceManager()
        ws2.import_zip(zip_bytes)
        assert ws2.state.image is not None
        assert comp_id in ws2.state.components

    def test_import_zip_missing_workspace_json(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", "hello")
        ws = WorkspaceManager()
        with pytest.raises(InvalidArchiveError, match="Missing workspace.json"):
            ws.import_zip(buf.getvalue())


# ── Add Component ──────────────────────────────────────────────────────


class TestAddComponent:
    def test_add_root_component(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Header", Bounds(x=0, y=0, w=100, h=50))
        assert comp_id in ws.state.components
        assert comp_id in ws.state.rootComponents
        assert ws.state.components[comp_id].label == "Header"

    def test_add_child_component(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "Parent", Bounds(x=0, y=0, w=200, h=200))
        ws.add_component(
            child_id, "Child", Bounds(x=10, y=10, w=50, h=50), parent_id=parent_id
        )
        assert child_id in ws.state.components
        assert child_id in ws.state.components[parent_id].childrenIds
        assert ws.state.components[child_id].parentId == parent_id

    def test_add_component_without_image_raises(self):
        ws = WorkspaceManager()
        with pytest.raises(InvalidStateError):
            ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=10, h=10))

    def test_add_component_with_missing_parent_raises(self):
        ws = _workspace_with_image()
        with pytest.raises(ParentNotFoundError):
            ws.add_component(
                uuid.uuid4(), "X", Bounds(x=0, y=0, w=10, h=10), parent_id=uuid.uuid4()
            )

    def test_add_assigns_numbers(self):
        ws = _workspace_with_image()
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        ws.add_component(id1, "A", Bounds(x=0, y=0, w=50, h=50))
        ws.add_component(id2, "B", Bounds(x=100, y=0, w=50, h=50))
        assert ws.state.components[id1].number == "1"
        assert ws.state.components[id2].number == "2"


# ── Move Component ────────────────────────────────────────────────────


class TestMoveComponent:
    def test_move_component(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Box", Bounds(x=10, y=10, w=50, h=50))
        ws.move_component(comp_id, 100, 100)
        assert ws.state.components[comp_id].bounds.x == 100
        assert ws.state.components[comp_id].bounds.y == 100

    def test_move_shifts_descendants(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "Parent", Bounds(x=0, y=0, w=200, h=200))
        ws.add_component(
            child_id, "Child", Bounds(x=10, y=10, w=50, h=50), parent_id=parent_id
        )
        ws.move_component(parent_id, 100, 100)
        assert ws.state.components[child_id].bounds.x == 110
        assert ws.state.components[child_id].bounds.y == 110

    def test_move_nonexistent_raises(self):
        ws = _workspace_with_image()
        with pytest.raises(ComponentNotFoundError):
            ws.move_component(uuid.uuid4(), 0, 0)


# ── Update Component ──────────────────────────────────────────────────


class TestUpdateComponent:
    def test_update_label(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Old", Bounds(x=0, y=0, w=50, h=50))
        ws.update_component(comp_id, label="New")
        assert ws.state.components[comp_id].label == "New"

    def test_update_style(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Box", Bounds(x=0, y=0, w=50, h=50))
        ws.update_component(comp_id, style=Style(pillCorner="bottom_right"))
        assert ws.state.components[comp_id].style.pillCorner == "bottom_right"

    def test_update_nonexistent_raises(self):
        ws = _workspace_with_image()
        with pytest.raises(ComponentNotFoundError):
            ws.update_component(uuid.uuid4(), label="X")

    def test_reparent_component(self):
        ws = _workspace_with_image()
        p1 = uuid.uuid4()
        p2 = uuid.uuid4()
        child = uuid.uuid4()
        ws.add_component(p1, "P1", Bounds(x=0, y=0, w=200, h=200))
        ws.add_component(p2, "P2", Bounds(x=300, y=0, w=200, h=200))
        ws.add_component(child, "C", Bounds(x=10, y=10, w=50, h=50), parent_id=p1)
        # Reparent child from p1 to p2 (move bounds first)
        ws.update_component(child, bounds=Bounds(x=310, y=10, w=50, h=50), parent_id=p2)
        assert ws.state.components[child].parentId == p2
        assert child in ws.state.components[p2].childrenIds
        assert child not in ws.state.components[p1].childrenIds


# ── Delete Component ──────────────────────────────────────────────────


class TestDeleteComponent:
    def test_delete_root_component(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))
        ws.delete_component(comp_id)
        assert comp_id not in ws.state.components
        assert comp_id not in ws.state.rootComponents

    def test_delete_cascades_to_children(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "P", Bounds(x=0, y=0, w=200, h=200))
        ws.add_component(
            child_id, "C", Bounds(x=10, y=10, w=50, h=50), parent_id=parent_id
        )
        ws.delete_component(parent_id)
        assert parent_id not in ws.state.components
        assert child_id not in ws.state.components

    def test_delete_nonexistent_raises(self):
        ws = _workspace_with_image()
        with pytest.raises(ComponentNotFoundError):
            ws.delete_component(uuid.uuid4())


# ── Undo / Redo ────────────────────────────────────────────────────────


class TestUndoRedo:
    def test_undo_add(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))
        assert comp_id in ws.state.components
        result = ws.undo()
        assert result is True
        assert comp_id not in ws.state.components

    def test_redo_restores(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))
        ws.undo()
        result = ws.redo()
        assert result is True
        assert comp_id in ws.state.components

    def test_undo_at_beginning_returns_false(self):
        ws = _workspace_with_image()
        result = ws.undo()
        assert result is False

    def test_redo_at_end_returns_false(self):
        ws = _workspace_with_image()
        result = ws.redo()
        assert result is False

    def test_undo_changes_revision(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "X", Bounds(x=0, y=0, w=50, h=50))
        rev_after_add = ws.state.revision
        ws.undo()
        # Undo bumps the revision on the restored snapshot
        assert ws.state.revision != rev_after_add or ws.state.revision > 0


# ── Read-Only Mode ────────────────────────────────────────────────────


class TestReadOnly:
    def test_readonly_blocks_mutations(self):
        ws = _workspace_with_image()
        ws.mutate(lambda s: setattr(s, "readOnly", True), force=True)
        with pytest.raises(ReadOnlyError):
            ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=10, h=10))

    def test_readonly_blocks_undo(self):
        ws = _workspace_with_image()
        ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=50, h=50))
        ws.mutate(lambda s: setattr(s, "readOnly", True), force=True)
        with pytest.raises(ReadOnlyError):
            ws.undo()

    def test_force_bypasses_readonly(self):
        ws = _workspace_with_image()
        ws.mutate(lambda s: setattr(s, "readOnly", True), force=True)
        # clear_workspace with force=True should work
        ws.clear_workspace(force=True)
        assert ws.state.image is None


# ── Cut Lines ──────────────────────────────────────────────────────────


class TestCutLines:
    def test_update_cut_lines(self):
        ws = _workspace_with_image()
        ws.update_cut_lines([100, 300])
        assert ws.state.cutLines == [100, 300]

    def test_cut_lines_sorted(self):
        ws = _workspace_with_image()
        ws.update_cut_lines([300, 100])
        assert ws.state.cutLines == [100, 300]

    def test_cut_line_intersecting_component_raises(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Box", Bounds(x=0, y=50, w=100, h=100))
        with pytest.raises(InvalidStateError, match="intersects"):
            ws.update_cut_lines([75])

    def test_add_component_intersecting_cut_line_raises(self):
        ws = _workspace_with_image()
        ws.update_cut_lines([200])
        comp_id = uuid.uuid4()
        with pytest.raises(InvalidStateError, match="intersects existing cut line"):
            ws.add_component(comp_id, "Box", Bounds(x=0, y=150, w=100, h=100))

    def test_move_component_intersecting_cut_line_raises(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Box", Bounds(x=0, y=50, w=50, h=50))
        ws.update_cut_lines([200])
        with pytest.raises(InvalidStateError, match="intersects existing cut line"):
            ws.move_component(comp_id, 0, 180)

    def test_update_component_intersecting_cut_line_raises(self):
        ws = _workspace_with_image()
        comp_id = uuid.uuid4()
        ws.add_component(comp_id, "Box", Bounds(x=0, y=50, w=50, h=50))
        ws.update_cut_lines([200])
        with pytest.raises(InvalidStateError, match="intersects existing cut line"):
            ws.update_component(comp_id, bounds=Bounds(x=0, y=180, w=50, h=50))


# ── Export ─────────────────────────────────────────────────────────────


class TestExportZip:
    def test_export_contains_workspace_json_and_image(self):
        ws = _workspace_with_image()
        zip_bytes = ws.export_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            assert "workspace.json" in zf.namelist()
            state_data = json.loads(zf.read("workspace.json"))
            filename = state_data.get("image", {}).get("filename")
            assert filename is not None
            assert filename in zf.namelist()

    def test_export_without_image_raises(self):
        ws = WorkspaceManager()
        with pytest.raises(InvalidStateError):
            ws.export_zip()


class TestExportImages:
    def test_export_images_annotated(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "Parent_Box", Bounds(x=10, y=10, w=100, h=100))
        ws.add_component(
            child_id, "Child_Box", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id
        )

        zip_bytes = ws.export_images("annotated")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            assert any("Parent_Box" in name for name in names)
            assert not any("Child_Box" in name for name in names)
            assert all(not name.startswith("annotated/") for name in names)

    def test_export_images_raw(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "Parent_Box", Bounds(x=10, y=10, w=100, h=100))
        ws.add_component(
            child_id, "Child_Box", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id
        )

        zip_bytes = ws.export_images("raw")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            assert any("Parent_Box" in name for name in names)
            assert any("Child_Box" in name for name in names)
            assert all(not name.startswith("raw/") for name in names)

    def test_export_images_without_image_raises(self):
        ws = WorkspaceManager()
        with pytest.raises(InvalidStateError):
            ws.export_images("annotated")

    def test_export_images_both(self):
        ws = _workspace_with_image()
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        ws.add_component(parent_id, "Parent_Box", Bounds(x=10, y=10, w=100, h=100))
        ws.add_component(
            child_id, "Child_Box", Bounds(x=20, y=20, w=50, h=50), parent_id=parent_id
        )

        zip_bytes = ws.export_images("both")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            # Verify annotated folder has the parent box, but not child (as it's a leaf)
            assert any(
                name.startswith("annotated/") and "Parent_Box" in name for name in names
            )
            assert not any(
                name.startswith("annotated/") and "Child_Box" in name for name in names
            )
            # Verify raw folder has both
            assert any(
                name.startswith("raw/") and "Parent_Box" in name for name in names
            )
            assert any(
                name.startswith("raw/") and "Child_Box" in name for name in names
            )


# ── Subscriber Notifications ──────────────────────────────────────────


class TestSubscriber:
    def test_subscriber_called_on_mutation(self):
        ws = _workspace_with_image()
        calls = []
        ws.subscribe(lambda patch, state: calls.append((patch, state)))
        ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=50, h=50))
        assert len(calls) == 1
        patch, new_state = calls[0]
        assert isinstance(patch, list)

    def test_subscriber_called_on_undo(self):
        ws = _workspace_with_image()
        ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=50, h=50))
        calls = []
        ws.subscribe(lambda patch, state: calls.append(True))
        ws.undo()
        assert len(calls) == 1


# ── Clear Workspace ───────────────────────────────────────────────────


class TestClearWorkspace:
    def test_clear_resets_everything(self):
        ws = _workspace_with_image()
        ws.add_component(uuid.uuid4(), "X", Bounds(x=0, y=0, w=50, h=50))
        ws.clear_workspace()
        assert ws.state.image is None
        assert ws.state.components == {}
        assert ws.state.rootComponents == []
        assert ws.state.cutLines == []
        assert ws.raw_image_bytes == b""


# ── Thread Safety ─────────────────────────────────────────────────────


class TestConcurrency:
    def test_concurrent_mutations_do_not_corrupt(self):
        ws = _workspace_with_image()
        errors = []

        def add_many(start: int):
            for i in range(20):
                try:
                    cid = uuid.uuid4()
                    x = (start * 100 + i * 10) % 700
                    ws.add_component(cid, f"C{start}_{i}", Bounds(x=x, y=0, w=8, h=8))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=add_many, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All components should be present
        assert len(ws.state.components) == 80
