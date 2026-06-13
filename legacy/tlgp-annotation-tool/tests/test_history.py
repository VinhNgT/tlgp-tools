"""Tests for HistoryManager undo/redo and snapshot behavior."""

import pytest
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.history import HistoryManager


def _make_session(**kwargs):
    return ScreenSession(screen_name="Test", **kwargs)


def _box(id, x1=0, y1=0, x2=100, y2=100):
    return AnnotationBox(id=id, label=f"Box {id}", x1=x1, y1=y1, x2=x2, y2=y2)


class TestHistoryInit:
    def test_initial_snapshot_saved(self):
        session = _make_session()
        hm = HistoryManager(session)
        assert hm.pointer == 0
        assert len(hm.history) == 1

    def test_initial_state_is_empty(self):
        session = _make_session()
        hm = HistoryManager(session)
        snapshot = hm.history[0]
        assert snapshot[0] == []  # components
        assert snapshot[1] == "Test"  # screen_name
        assert snapshot[2] == ""  # description
        assert snapshot[3] == []  # cut_lines


class TestHistorySaveSnapshot:
    def test_save_increments_pointer(self):
        session = _make_session()
        hm = HistoryManager(session)
        session.components.append(_box(1))
        hm.save_snapshot()
        assert hm.pointer == 1
        assert len(hm.history) == 2

    def test_save_after_undo_discards_redo(self):
        """Saving a snapshot after undo should discard forward history."""
        session = _make_session()
        hm = HistoryManager(session)

        session.components.append(_box(1))
        hm.save_snapshot()  # pointer=1

        session.components.append(_box(2))
        hm.save_snapshot()  # pointer=2

        hm.undo()  # pointer=1
        assert hm.pointer == 1

        session.components.append(_box(3))
        hm.save_snapshot()  # pointer=2, but forward history discarded
        assert hm.pointer == 2
        assert len(hm.history) == 3

    def test_deep_copy_isolation(self):
        """Modifying session after save should not affect the snapshot."""
        session = _make_session()
        hm = HistoryManager(session)

        box = _box(1)
        session.components.append(box)
        hm.save_snapshot()

        # Modify the box after snapshot
        box.label = "Modified"
        assert hm.history[1][0][0].label == "Box 1"  # snapshot is unaffected


class TestHistoryUndo:
    def test_undo_restores_components(self):
        session = _make_session()
        hm = HistoryManager(session)

        session.components.append(_box(1))
        hm.save_snapshot()
        assert len(session.components) == 1

        hm.undo()
        assert len(session.components) == 0

    def test_undo_restores_screen_name(self):
        session = _make_session()
        hm = HistoryManager(session)

        session.screen_name = "Changed"
        hm.save_snapshot()

        hm.undo()
        assert session.screen_name == "Test"

    def test_undo_restores_cut_lines(self):
        session = _make_session()
        hm = HistoryManager(session)

        session.cut_lines = [300, 700]
        hm.save_snapshot()

        hm.undo()
        assert session.cut_lines == []

    def test_undo_at_beginning_returns_false(self):
        session = _make_session()
        hm = HistoryManager(session)
        assert hm.undo() is False

    def test_multiple_undos(self):
        session = _make_session()
        hm = HistoryManager(session)

        for i in range(5):
            session.components.append(_box(i + 1))
            hm.save_snapshot()

        assert len(session.components) == 5

        for expected_count in [4, 3, 2, 1, 0]:
            hm.undo()
            assert len(session.components) == expected_count


class TestHistoryRedo:
    def test_redo_after_undo(self):
        session = _make_session()
        hm = HistoryManager(session)

        session.components.append(_box(1))
        hm.save_snapshot()

        hm.undo()
        assert len(session.components) == 0

        hm.redo()
        assert len(session.components) == 1

    def test_redo_at_end_returns_false(self):
        session = _make_session()
        hm = HistoryManager(session)
        assert hm.redo() is False

    def test_undo_redo_round_trip(self):
        session = _make_session()
        hm = HistoryManager(session)

        session.screen_name = "V2"
        session.description = "Desc V2"
        session.cut_lines = [500]
        hm.save_snapshot()

        hm.undo()
        assert session.screen_name == "Test"
        assert session.description == ""
        assert session.cut_lines == []

        hm.redo()
        assert session.screen_name == "V2"
        assert session.description == "Desc V2"
        assert session.cut_lines == [500]
