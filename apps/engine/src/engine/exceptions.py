class EngineException(Exception):
    """Base exception for all engine-related errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.message = message
        self.details = kwargs

    def __str__(self):
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ComponentNotFoundError(EngineException):
    """Raised when a component is not found in the workspace."""

    pass


class ParentNotFoundError(EngineException):
    """Raised when a parent component is not found in the workspace."""

    pass


class InvalidArchiveError(EngineException):
    """Raised when the imported archive/zip is invalid."""

    pass


class InvalidImageError(EngineException):
    """Raised when the uploaded image is invalid."""

    pass


class InvalidStateError(EngineException):
    """Raised when the workspace is in an invalid state for the requested operation."""

    pass


class UndoRedoError(EngineException):
    """Raised when an undo or redo operation is not possible."""

    pass
