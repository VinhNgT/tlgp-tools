"""Workspace error hierarchy.

All workspace-domain exceptions inherit from WorkspaceError,
enabling centralized error handling in the FastAPI exception handler.
"""


class WorkspaceError(Exception):
    """Base exception for all workspace-related errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.message = message
        self.details = kwargs

    def __str__(self):
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ComponentNotFoundError(WorkspaceError):
    """Raised when a component is not found in the workspace."""

    pass


class ParentNotFoundError(WorkspaceError):
    """Raised when a parent component is not found in the workspace."""

    pass


class InvalidArchiveError(WorkspaceError):
    """Raised when the imported archive/zip is invalid."""

    pass


class InvalidImageError(WorkspaceError):
    """Raised when the uploaded image is invalid."""

    pass


class InvalidStateError(WorkspaceError):
    """Raised when the workspace is in an invalid state for the requested operation."""

    pass


class UndoRedoError(WorkspaceError):
    """Raised when an undo or redo operation is not possible."""

    pass


class BoundaryViolationError(WorkspaceError):
    """Raised when a component's bounds violate its parent-child boundary constraints."""

    pass


class ReadOnlyError(WorkspaceError):
    """Raised when a mutation is attempted on a read-only workspace."""

    pass
