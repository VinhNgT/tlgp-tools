"""Callback containers for the GUI components."""

from collections.abc import Callable
from uuid import UUID


class CanvasCallbacks:
    """Callbacks emitted by the AnnotationCanvasView."""

    def __init__(self):
        self.on_component_moved: Callable[[str, int, int], None] | None = None
        self.on_component_resized: Callable[[str, dict], None] | None = None
        self.on_component_created: Callable[[dict], None] | None = None
        self.on_active_interaction_changed: Callable[[dict | None], None] | None = None
        self.on_viewport_change_request: Callable[[float, tuple], None] | None = None
        self.on_request_context_menu: Callable[[int, int], None] | None = None
        self.on_drill_into: Callable[[UUID], None] | None = None
        self.on_drill_out: Callable[[], None] | None = None
        self.on_import_zip: Callable[[], None] | None = None
        self.on_import_image: Callable[[], None] | None = None


class AppCallbacks:
    """Callbacks emitted by the MainAppWindow."""

    def __init__(self):
        self.on_mode_change_request: Callable[[str], None] | None = None
        self.on_undo_request: Callable[[], None] | None = None
        self.on_redo_request: Callable[[], None] | None = None
        self.on_delete_request: Callable[[], None] | None = None
        self.on_back_request: Callable[[], None] | None = None
        self.on_import_zip_request: Callable[[], None] | None = None
        self.on_import_image_request: Callable[[], None] | None = None
        self.on_export_zip_request: Callable[[], None] | None = None
        self.on_open_cut_editor_request: Callable[[], None] | None = None
        self.on_open_screen_info_request: Callable[[], None] | None = None
        self.on_enter_pressed: Callable[[], str | None] | None = None
        self.on_escape_pressed: Callable[[], str | None] | None = None
        self.on_arrow_key_pressed: Callable[[int, int], None] | None = None
        self.on_sidebar_context_menu: Callable[[UUID, int, int], None] | None = None
        self.on_sidebar_rename_request: Callable[[UUID, str], None] | None = None
