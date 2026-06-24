from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from tlgp_logger import get_logger

from annotator.models import Bounds, WorkspaceState

logger = get_logger(__name__)


@dataclass
class UIState:
    selected_component_ids: list[UUID] = field(default_factory=list)
    current_mode: str = "select"  # select, draw, pan
    zoom_factor: float = 1.0
    pan_offset: tuple[float, float] = (0.0, 0.0)
    viewport_size: tuple[int, int] = (800, 600)
    parent_stack: list[UUID] = field(default_factory=list)
    workspace_state: WorkspaceState | None = None
    text_focused: bool = False
    active_interaction: dict[UUID, Bounds] | None = None


class UIStateStore:
    def __init__(self):
        self._state = UIState()
        self._listeners: dict[str, list[Callable[[], None]]] = defaultdict(list)

    @property
    def state(self) -> UIState:
        return self._state

    def subscribe(self, event_type: str, callback: Callable[[], None]):
        """Register a callback for updates to a specific state slice (e.g. selection, viewport, workspace)."""
        self._listeners[event_type].append(callback)

    def notify(self, event_type: str):
        """Notify all subscribers registered to the given state slice."""
        for callback in self._listeners[event_type]:
            try:
                callback()
            except Exception:
                logger.exception("Error in state change subscriber")

    def update_state(self, event_type: str, **kwargs):
        """Update fields in UIState and trigger the corresponding event notification if a value changed."""
        changed = False
        for key, val in kwargs.items():
            if hasattr(self._state, key):
                if getattr(self._state, key) != val:
                    setattr(self._state, key, val)
                    changed = True
        if changed:
            self.notify(event_type)
