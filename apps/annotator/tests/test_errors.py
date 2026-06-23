"""Tests for annotator.workspace.errors (WorkspaceError hierarchy)."""

from annotator.workspace.errors import (
    BoundaryViolationError,
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
    UndoRedoError,
    WorkspaceError,
)


class TestWorkspaceError:
    def test_base_error_message(self):
        err = WorkspaceError("test message")
        assert err.message == "test message"
        assert str(err) == "test message"
        assert err.details == {}

    def test_base_error_with_details(self):
        err = WorkspaceError("test", component_id="abc", extra="data")
        assert err.details == {"component_id": "abc", "extra": "data"}
        assert "details:" in str(err)

    def test_subclass_hierarchy(self):
        subclasses = [
            ComponentNotFoundError,
            ParentNotFoundError,
            InvalidArchiveError,
            InvalidImageError,
            InvalidStateError,
            UndoRedoError,
            BoundaryViolationError,
            ReadOnlyError,
        ]
        for cls in subclasses:
            err = cls("error message", key="value")
            assert isinstance(err, WorkspaceError)
            assert err.message == "error message"
            assert err.details == {"key": "value"}

    def test_catchable_as_base(self):
        """All workspace errors are catchable via the base class."""
        try:
            raise ComponentNotFoundError("not found", component_id="123")
        except WorkspaceError as e:
            assert e.message == "not found"
            assert e.details["component_id"] == "123"
