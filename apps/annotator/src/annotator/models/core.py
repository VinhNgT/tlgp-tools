"""Annotator domain models — re-exported from the shared contracts package.

The canonical schema definitions live in `tlgp_contracts.workspace`.
This module re-exports them so that existing annotator code continues to
work via `from annotator.models import WorkspaceState` without changes.
"""

from tlgp_contracts.workspace import (
    Bounds,
    Component,
    ImageInfo,
    PillCorner,
    ScreenInfo,
    Style,
    WorkspaceState,
)

__all__ = [
    "Bounds",
    "Component",
    "ImageInfo",
    "PillCorner",
    "ScreenInfo",
    "Style",
    "WorkspaceState",
]
