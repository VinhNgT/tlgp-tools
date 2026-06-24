"""State machine container for the gesture handlers."""

from uuid import UUID

from annotator.gui.transformer import ViewportTransformer


class GestureState:
    """Holds shared state for the gesture interaction lifecycle."""

    def __init__(self, transformer: ViewportTransformer):
        self.transformer = transformer

        # Click state
        self.last_click_time: float = 0.0
        self.last_click_cx: float = 0.0
        self.last_click_cy: float = 0.0
        self.click_sequence_count: int = 1
        self.cycle_components: list | None = None
        self.last_cycle_index: int = 0

        # Drag state
        self.is_dragging: bool = False
        self.resize_handle: str | None = None
        self.drag_mouse_start_abs: tuple[float, float] = (0.0, 0.0)
        self.drag_orig_bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.drag_orig_descendants: dict[UUID, tuple[float, float, float, float]] = {}

        # Marquee / Draw state
        self.has_temp_rect: bool = False
        self.draw_start_x: float = 0.0
        self.draw_start_y: float = 0.0

        # Pan state
        self.space_panning: bool = False
        self.pan_start_mouse: tuple[float, float] = (0.0, 0.0)
        self.pan_start_offset: tuple[float, float] = (0.0, 0.0)

