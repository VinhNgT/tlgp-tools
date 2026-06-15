"""Custom exceptions for the MCP Server."""

from __future__ import annotations


class ApiClientError(Exception):
    """
    Rich exception class for wrapping low-level HTTP/transport errors.
    Captures status codes, URLs, and backend error details to provide
    contextual error handling and logging.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        url: str | None = None,
        method: str | None = None,
        backend_detail: str | dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.url = url
        self.method = method
        self.backend_detail = backend_detail

    def __str__(self) -> str:
        base = f"ApiClientError: {self.message}"
        if self.status_code:
            base += f" [Status: {self.status_code}]"
        if self.method and self.url:
            base += f" ({self.method} {self.url})"
        if self.backend_detail:
            base += f" | Backend Detail: {self.backend_detail}"
        return base

    def to_dict(self) -> dict:
        """Serialize the error context for JSON-RPC payloads."""
        return {
            "error": "ApiClientError",
            "message": self.message,
            "status_code": self.status_code,
            "url": self.url,
            "method": self.method,
            "backend_detail": self.backend_detail,
        }
