"""State management and callbacks for the Cut Editor."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CutEditorState:
    """Holds the UI state for the cut editor dialog."""
    cut_lines: list[int] = field(default_factory=list)
    hover_y: float | None = None
    drag_index: int = -1
    last_valid_drag_y: int = 0
    mode: str = "idle"

class CutEditorCallbacks:
    """Callback hooks for the cut editor."""
    on_cuts_changed: Callable[[], None] | None = None
    on_hover_changed: Callable[[], None] | None = None
    on_drag_state_changed: Callable[[], None] | None = None

