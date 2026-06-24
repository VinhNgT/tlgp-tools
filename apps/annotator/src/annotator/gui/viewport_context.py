"""Immutable viewport state snapshot for coordinate mapping operations.

Captures all parameters needed by ViewportTransformer methods,
eliminating the need to pass 5–6 individual arguments per call.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ViewportContext:
    """Frozen snapshot of viewport state used for coordinate transformations.

    Constructed once per event/frame and passed to transformer convenience
    methods, collapsing repetitive argument lists throughout canvas and
    gesture code.
    """

    zoom_factor: float
    parent_stack: tuple[UUID, ...]
    cut_lines: tuple[int, ...]
    pan_offset: tuple[float, float]
