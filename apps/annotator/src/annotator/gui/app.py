"""Main application window — PySide6 QMainWindow.

Provides the toolbar, menu bar, sidebar splitter, and canvas area.
All user interaction is delegated to the controller via callbacks.
"""


from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .canvas import AnnotationCanvasView
from .properties import ComponentPropertiesView
from .sidebar import SidebarTreeView
from .transformer import ViewportTransformer


class WelcomeWidget(QWidget):
    """Welcome screen displayed when no image is loaded."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.on_import_zip = None
        self.on_import_image = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedSize(400, 220)
        card.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 25, 30, 25)
        card_layout.setSpacing(10)

        title = QLabel("Annotator")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: white; border: none;")
        card_layout.addWidget(title)

        self.desc_label = QLabel("Open a workspace session or raw image to begin.")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 10pt; color: #888888; border: none;")
        card_layout.addWidget(self.desc_label)

        card_layout.addSpacing(10)

        btn_style = """
            QPushButton {
                background-color: #0c8ce9;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #1a9cf5;
            }
            QPushButton:pressed {
                background-color: #0a6fc0;
            }
        """

        self.btn_zip = QPushButton("Import Workspace (.zip)")
        self.btn_zip.setStyleSheet(btn_style)
        self.btn_zip.clicked.connect(self._on_import_zip)
        card_layout.addWidget(self.btn_zip)

        self.btn_img = QPushButton("Import Raw Image")
        self.btn_img.setStyleSheet(btn_style)
        self.btn_img.clicked.connect(self._on_import_image)
        card_layout.addWidget(self.btn_img)

        layout.addWidget(card)

        self.setStyleSheet("background-color: #121212;")



    def _on_import_zip(self):
        if self.on_import_zip:
            self.on_import_zip()

    def _on_import_image(self):
        if self.on_import_image:
            self.on_import_image()


class MainAppWindow(QMainWindow):
    """Main application shell providing toolbar, sidebar, and canvas layout.

    All user interactions are delegated to the controller via callback attributes.
    """

    def __init__(self, transformer: ViewportTransformer | None = None):
        super().__init__()
        self.setWindowTitle("Annotator")
        self.resize(1400, 900)
        self.setMinimumSize(800, 600)

        # ── Callback attributes (set by controller) ───────────────
        self.on_mode_change_request = None
        self.on_undo_request = None
        self.on_redo_request = None
        self.on_delete_request = None
        self.on_back_request = None
        self.on_import_zip_request = None
        self.on_import_image_request = None
        self.on_export_zip_request = None
        self.on_open_cut_editor_request = None
        self.on_open_screen_info_request = None
        self.on_enter_pressed = None
        self.on_escape_pressed = None
        self.on_arrow_key_pressed = None

        # ── Build UI ──────────────────────────────────────────────
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_area(transformer)

    def _build_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        act_import_zip = QAction("Import Workspace (.zip)", self)
        act_import_zip.setShortcut(QKeySequence("Ctrl+O"))
        act_import_zip.triggered.connect(lambda: self._fire(self.on_import_zip_request))
        file_menu.addAction(act_import_zip)

        act_import_img = QAction("Import Raw Image", self)
        act_import_img.triggered.connect(lambda: self._fire(self.on_import_image_request))
        file_menu.addAction(act_import_img)

        act_export = QAction("Export Session (.zip)", self)
        act_export.setShortcut(QKeySequence("Ctrl+S"))
        act_export.triggered.connect(lambda: self._fire(self.on_export_zip_request))
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_screen_info = QAction("Screen Info…", self)
        act_screen_info.triggered.connect(lambda: self._fire(self.on_open_screen_info_request))
        file_menu.addAction(act_screen_info)

        act_cuts = QAction("Edit Cut Lines…", self)
        act_cuts.setShortcut(QKeySequence("Ctrl+L"))
        act_cuts.triggered.connect(lambda: self._fire(self.on_open_cut_editor_request))
        file_menu.addAction(act_cuts)

        edit_menu = menubar.addMenu("&Edit")

        act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        act_undo.triggered.connect(lambda: self._fire(self.on_undo_request))
        edit_menu.addAction(act_undo)

        act_redo = QAction("Redo", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        act_redo.triggered.connect(lambda: self._fire(self.on_redo_request))
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_delete = QAction("Delete", self)
        act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        act_delete.triggered.connect(lambda: self._fire(self.on_delete_request))
        edit_menu.addAction(act_delete)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        # Mode selector
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)

        modes = [
            ("V", "select", "Select mode (V)"),
            ("R", "draw", "Draw mode (R)"),
            ("H", "pan", "Pan mode (H)"),
        ]
        self._mode_actions: dict[str, QAction] = {}
        for key, mode, tooltip in modes:
            action = QAction(key, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.setData(mode)
            action.triggered.connect(lambda checked, m=mode: self._on_mode_toggled(m))
            self.mode_group.addAction(action)
            tb.addAction(action)
            self._mode_actions[mode] = action
        self._mode_actions["select"].setChecked(True)

        tb.addSeparator()

        # Back button
        self.btn_back = QAction("← Back", self)
        self.btn_back.setToolTip("Go back (Escape)")
        self.btn_back.triggered.connect(lambda: self._fire(self.on_back_request))
        tb.addAction(self.btn_back)

        # Breadcrumbs label
        self.lbl_breadcrumbs = QLabel("Root")
        self.lbl_breadcrumbs.setStyleSheet("color: #888888; padding: 0 8px;")
        tb.addWidget(self.lbl_breadcrumbs)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        # Zoom display
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("color: #888888; padding: 0 8px;")
        tb.addWidget(self.lbl_zoom)

    def _build_central_area(self, transformer: ViewportTransformer | None):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left: canvas stack (welcome or annotation)
        self.canvas_stack = QStackedWidget()
        self.welcome = WelcomeWidget()
        self.welcome.on_import_zip = lambda: self._fire(self.on_import_zip_request)
        self.welcome.on_import_image = lambda: self._fire(self.on_import_image_request)
        self.canvas = AnnotationCanvasView(transformer=transformer)
        self.canvas_stack.addWidget(self.welcome)
        self.canvas_stack.addWidget(self.canvas)
        self.canvas_stack.setCurrentWidget(self.welcome)

        splitter.addWidget(self.canvas_stack)

        # Right: sidebar + properties
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self.tree = SidebarTreeView()
        right_splitter.addWidget(self.tree)

        self.properties = ComponentPropertiesView()
        right_splitter.addWidget(self.properties)

        right_splitter.setSizes([400, 300])
        right_layout.addWidget(right_splitter)

        splitter.addWidget(right_panel)
        splitter.setSizes([1000, 300])

    # ── Public API (called by controller) ─────────────────────────────

    def set_canvas_image(self, img):
        """Switch between welcome screen and annotation canvas."""
        if img is None:
            self.canvas_stack.setCurrentWidget(self.welcome)
        else:
            self.canvas.set_background_image(img)
            self.canvas_stack.setCurrentWidget(self.canvas)

    def set_mode_str(self, mode: str):
        """Update toolbar mode buttons to match the given mode."""
        action = self._mode_actions.get(mode)
        if action:
            action.setChecked(True)

    def update_status(self, text: str, is_error: bool = False):
        self.properties.update_status(text, is_error)

    def update_zoom_display(self, zoom_factor: float):
        pct = round(zoom_factor * 100)
        self.lbl_zoom.setText(f"{pct}%")

    def update_breadcrumbs(self, breadcrumbs: list[str]):
        if breadcrumbs:
            path = " › ".join(["Root"] + breadcrumbs)
        else:
            path = "Root"
        self.lbl_breadcrumbs.setText(path)

    def show_context_menu(self, x: int, y: int, actions: list[dict]):
        """Display a popup context menu at screen coordinates (x, y)."""
        menu = QMenu(self)
        for item in actions:
            if item.get("separator"):
                menu.addSeparator()
            else:
                act = menu.addAction(item["label"])
                act.triggered.connect(item["command"])
        menu.exec(QPoint(x, y))

    def is_text_focused(self) -> bool:
        """Check if any text entry in properties is focused."""
        return self.properties.is_text_focused()



    # ── Keyboard Handling ─────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # Avoid intercepting shortcuts when text is focused
        if self.properties.is_text_focused():
            super().keyPressEvent(event)
            return

        # Mode shortcuts
        if key == Qt.Key.Key_V and not has_ctrl:
            self._on_mode_toggled("select")
            self._mode_actions["select"].setChecked(True)
            return
        if key == Qt.Key.Key_R and not has_ctrl:
            self._on_mode_toggled("draw")
            self._mode_actions["draw"].setChecked(True)
            return
        if key == Qt.Key.Key_H and not has_ctrl:
            self._on_mode_toggled("pan")
            self._mode_actions["pan"].setChecked(True)
            return

        # Navigation
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if self.on_enter_pressed:
                result = self.on_enter_pressed()
                if result == "break":
                    return

        if key == Qt.Key.Key_Escape:
            if self.on_escape_pressed:
                result = self.on_escape_pressed()
                if result == "break":
                    return

        # Arrow keys (nudge)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            dx, dy = 0, 0
            if key == Qt.Key.Key_Left:
                dx = -1
            elif key == Qt.Key.Key_Right:
                dx = 1
            elif key == Qt.Key.Key_Up:
                dy = -1
            elif key == Qt.Key.Key_Down:
                dy = 1
            if self.on_arrow_key_pressed:
                self.on_arrow_key_pressed(dx, dy)
            return

        # Canvas shortcuts
        if key == Qt.Key.Key_F:
            self.canvas.fit_to_screen()
            return
        if key == Qt.Key.Key_T:
            self.canvas.toggle_labels_visibility()
            return
        if key == Qt.Key.Key_C:
            self.canvas.zoom_focus_target()
            return
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            if self.on_delete_request:
                self.on_delete_request()
            return

        super().keyPressEvent(event)

    # ── Private ──────────────────────────────────────────────────────

    def _on_mode_toggled(self, mode: str):
        if self.on_mode_change_request:
            self.on_mode_change_request(mode)



    @staticmethod
    def _fire(callback):
        if callback:
            callback()
