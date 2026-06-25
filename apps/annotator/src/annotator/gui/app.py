"""Main application window — PySide6 QMainWindow.

Provides the toolbar, menu bar, sidebar splitter, and canvas area.
All user interaction is delegated to the controller via callbacks.
"""

import os

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .callbacks import AppCallbacks
from .canvas import AnnotationCanvasView
from .properties import ComponentPropertiesView
from .sidebar import SidebarTreeView
from .transformer import ViewportTransformer


class WelcomeWidget(QWidget):
    """Fallback canvas display shown when no image or workspace is imported."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeScreen")

        self.on_import_zip = None
        self.on_import_image = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("WelcomeCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setFrameShadow(QFrame.Shadow.Raised)
        card.setFixedSize(400, 220)

        card_layout = QVBoxLayout(card)

        title = QLabel("Annotator")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        card_layout.addWidget(title)

        self.desc_label = QLabel("Open a workspace or raw image to begin.")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setWordWrap(True)
        card_layout.addWidget(self.desc_label)

        card_layout.addSpacing(10)

        self.btn_zip = QPushButton("Import Workspace (.zip)")
        self.btn_zip.clicked.connect(self._on_import_zip)
        card_layout.addWidget(self.btn_zip)

        self.btn_img = QPushButton("Import Raw Image")
        self.btn_img.clicked.connect(self._on_import_image)
        card_layout.addWidget(self.btn_img)

        layout.addWidget(card)

    def _on_import_zip(self):
        if self.on_import_zip:
            self.on_import_zip()

    def _on_import_image(self):
        if self.on_import_image:
            self.on_import_image()


class GlobalFocusAndSelectionFilter(QObject):
    """Universal event filter that clears input focus and label text selections
    when clicking outside of them anywhere in the application.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            is_widget = isinstance(obj, QWidget)

            # 1. Unfocus any active text input widget on outside click
            focused = QApplication.focusWidget()
            if focused and focused.__class__.__name__ in (
                "QLineEdit",
                "QTextEdit",
                "QPlainTextEdit",
            ):
                if not is_widget or obj != focused:
                    try:
                        if not is_widget or not focused.isAncestorOf(obj):
                            focused.clearFocus()
                    except TypeError:
                        focused.clearFocus()

            # 2. Deselect/clear highlight on any selectable QLabels on outside click
            main_win = self.parent()
            if main_win:
                for label in main_win.findChildren(QLabel):
                    if (
                        label.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextSelectableByMouse
                    ):
                        if not is_widget or (
                            obj != label and not label.isAncestorOf(obj)
                        ):
                            label.setSelection(0, 0)

        return super().eventFilter(obj, event)


class MainAppWindow(QMainWindow):
    """Main application shell providing toolbar, sidebar, and canvas layout.

    All user interactions are delegated to the controller via callback attributes.
    """

    def __init__(self, transformer: ViewportTransformer | None = None):
        super().__init__()
        self.setWindowTitle("Annotator")

        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1400, 900)
        self.setMinimumSize(800, 600)

        # ── Callback attributes (set by controller) ───────────────
        self.callbacks = AppCallbacks()

        # Install global focus-out event filter to unfocus inputs on click outside
        self.focus_filter = GlobalFocusAndSelectionFilter(self)
        QApplication.instance().installEventFilter(self.focus_filter)

        # ── Build UI ──────────────────────────────────────────────
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_area(transformer)

    def _build_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        act_import_zip = QAction("Import Workspace (.zip)", self)
        act_import_zip.setShortcut(QKeySequence("Ctrl+O"))
        act_import_zip.triggered.connect(
            lambda: self._fire(self.callbacks.on_import_zip_request)
        )
        file_menu.addAction(act_import_zip)

        act_import_img = QAction("Import Raw Image", self)
        act_import_img.triggered.connect(
            lambda: self._fire(self.callbacks.on_import_image_request)
        )
        file_menu.addAction(act_import_img)

        self.act_export = QAction("Export Workspace (.zip)", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+S"))
        self.act_export.setEnabled(False)
        self.act_export.triggered.connect(
            lambda: self._fire(self.callbacks.on_export_zip_request)
        )
        file_menu.addAction(self.act_export)

        self.act_export_images = QAction("Export Images…", self)
        self.act_export_images.setEnabled(False)
        self.act_export_images.triggered.connect(
            lambda: self._fire(self.callbacks.on_export_images_request)
        )
        file_menu.addAction(self.act_export_images)

        file_menu.addSeparator()

        self.act_screen_info = QAction("Screen Info…", self)
        self.act_screen_info.setEnabled(False)
        self.act_screen_info.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_screen_info_request)
        )
        file_menu.addAction(self.act_screen_info)

        self.act_cuts = QAction("Edit Cut Lines…", self)
        self.act_cuts.setShortcut(QKeySequence("Ctrl+L"))
        self.act_cuts.setEnabled(False)
        self.act_cuts.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_cut_editor_request)
        )
        file_menu.addAction(self.act_cuts)

        edit_menu = menubar.addMenu("&Edit")

        self.act_undo = QAction("Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setEnabled(False)
        self.act_undo.triggered.connect(
            lambda: self._fire(self.callbacks.on_undo_request)
        )
        edit_menu.addAction(self.act_undo)

        self.act_redo = QAction("Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.setEnabled(False)
        self.act_redo.triggered.connect(
            lambda: self._fire(self.callbacks.on_redo_request)
        )
        edit_menu.addAction(self.act_redo)

        edit_menu.addSeparator()

        self.act_delete = QAction("Delete", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.setEnabled(False)
        self.act_delete.triggered.connect(
            lambda: self._fire(self.callbacks.on_delete_request)
        )
        edit_menu.addAction(self.act_delete)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        # Mode selector
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)

        modes = [
            ("Select (V)", "select", "Select mode (V)"),
            ("Draw (R)", "draw", "Draw mode (R)"),
            ("Pan (H)", "pan", "Pan mode (H)"),
        ]
        self._mode_actions: dict[str, QAction] = {}
        for key, mode, tooltip in modes:
            action = QAction(key, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.setData(mode)
            action.setEnabled(False)
            action.triggered.connect(lambda checked, m=mode: self._on_mode_toggled(m))
            self.mode_group.addAction(action)
            tb.addAction(action)
            self._mode_actions[mode] = action
        self._mode_actions["select"].setChecked(True)

        tb.addSeparator()

        # Fit button
        self.btn_fit = QAction("Fit", self)
        self.btn_fit.setToolTip("Fit active container to screen (F)")
        self.btn_fit.setEnabled(False)
        self.btn_fit.triggered.connect(lambda: self.canvas.fit_to_screen())
        tb.addAction(self.btn_fit)

        # Back button
        self.btn_back = QAction("← Back", self)
        self.btn_back.setToolTip("Go back (Escape)")
        self.btn_back.setEnabled(False)
        self.btn_back.triggered.connect(
            lambda: self._fire(self.callbacks.on_back_request)
        )
        tb.addAction(self.btn_back)

        # Spacing
        back_spacer = QWidget()
        back_spacer.setFixedWidth(6)
        tb.addWidget(back_spacer)

        # Breadcrumbs label
        self.lbl_breadcrumbs = QLabel("Root")
        tb.addWidget(self.lbl_breadcrumbs)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        # Show Labels checkbox
        self.chk_show_labels = QCheckBox("Show Labels")
        self.chk_show_labels.setToolTip("Toggle Labels (T)")
        self.chk_show_labels.setChecked(True)
        self.chk_show_labels.setEnabled(False)
        self.chk_show_labels.toggled.connect(self._on_show_labels_toggled)
        tb.addWidget(self.chk_show_labels)

        tb.addSeparator()

        # Cut Lines button
        self.btn_cut_lines = QAction("Cut Lines", self)
        self.btn_cut_lines.setToolTip("Edit Cut Lines (Ctrl+L)")
        self.btn_cut_lines.setEnabled(False)
        self.btn_cut_lines.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_cut_editor_request)
        )
        tb.addAction(self.btn_cut_lines)

        # Screen Info button
        self.btn_screen_info = QAction("Screen Info", self)
        self.btn_screen_info.setToolTip("View/Edit Screen Info")
        self.btn_screen_info.setEnabled(False)
        self.btn_screen_info.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_screen_info_request)
        )
        tb.addAction(self.btn_screen_info)

        tb.addSeparator()

        # Export images button
        self.btn_export_images = QAction("Export images", self)
        self.btn_export_images.setToolTip("Export screenshots and component images")
        self.btn_export_images.setEnabled(False)
        self.btn_export_images.triggered.connect(
            lambda: self._fire(self.callbacks.on_export_images_request)
        )
        tb.addAction(self.btn_export_images)
        btn_widget = tb.widgetForAction(self.btn_export_images)
        if btn_widget:
            btn_widget.setObjectName("PrimaryButton")

    def _build_central_area(self, transformer: ViewportTransformer | None):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # 1. Left: Tree
        self.tree = SidebarTreeView()
        splitter.addWidget(self.tree)

        # 2. Center: Canvas with overlay welcome widget
        self.canvas = AnnotationCanvasView(transformer=transformer)

        self.welcome = WelcomeWidget(self.canvas)
        self.welcome.on_import_zip = lambda: self._fire(
            self.callbacks.on_import_zip_request
        )
        self.welcome.on_import_image = lambda: self._fire(
            self.callbacks.on_import_image_request
        )

        canvas_layout = QVBoxLayout(self.canvas)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(self.welcome)

        splitter.addWidget(self.canvas)

        # 3. Right: Properties
        self.properties = ComponentPropertiesView()
        splitter.addWidget(self.properties)

        # Set initial sizes (Tree, Canvas, Properties)
        splitter.setSizes([250, 850, 300])

    # ── Public API (called by controller) ─────────────────────────────

    def set_canvas_image(self, img):
        """Toggle between welcome screen and annotation canvas."""
        has_img = img is not None
        if not has_img:
            self.welcome.show()
            self.canvas.set_background_image(None)
        else:
            self.welcome.hide()
            self.canvas.set_background_image(img)
            self.canvas.setFocus()

        # Data-driven widget enable/disable
        self.btn_cut_lines.setEnabled(has_img)
        self.chk_show_labels.setEnabled(has_img)
        self.btn_screen_info.setEnabled(has_img)
        self.btn_export_images.setEnabled(has_img)
        self.btn_fit.setEnabled(has_img)

        for action in self._mode_actions.values():
            action.setEnabled(has_img)

        self.act_export.setEnabled(has_img)
        self.act_export_images.setEnabled(has_img)
        self.act_screen_info.setEnabled(has_img)
        self.act_cuts.setEnabled(has_img)
        self.act_undo.setEnabled(has_img)
        self.act_redo.setEnabled(has_img)
        self.act_delete.setEnabled(has_img)

    def set_mode_str(self, mode: str):
        """Update toolbar mode buttons to match the given mode."""
        action = self._mode_actions.get(mode)
        if action:
            action.setChecked(True)

    def update_status(self, text: str, is_error: bool = False):
        self.properties.update_status(text, is_error)

    def update_breadcrumbs(self, breadcrumbs: list[str]):
        if breadcrumbs:
            path = " › ".join(["Root", *breadcrumbs])
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

        # Avoid intercepting shortcuts if no image is loaded
        if not self.canvas.full_pil_img:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.canvas.keyPressEvent(event)
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
            if self.callbacks.on_enter_pressed:
                result = self.callbacks.on_enter_pressed()
                if result == "break":
                    return

        if key == Qt.Key.Key_Escape:
            if self.callbacks.on_escape_pressed:
                result = self.callbacks.on_escape_pressed()
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
            if self.callbacks.on_arrow_key_pressed:
                self.callbacks.on_arrow_key_pressed(dx, dy)
            return

        # Canvas shortcuts
        if key == Qt.Key.Key_F:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.canvas.zoom_focus_target()
            else:
                self.canvas.fit_to_screen()
            return
        if key == Qt.Key.Key_T:
            self.canvas.toggle_labels_visibility()
            self.chk_show_labels.setChecked(self.canvas.show_labels)
            return
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            if self.callbacks.on_delete_request:
                self.callbacks.on_delete_request()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self.properties.is_text_focused() and self.canvas.full_pil_img:
                self.canvas.keyReleaseEvent(event)
                return
        super().keyReleaseEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.canvas.full_pil_img:
            self.canvas.setFocus()

    # ── Private ──────────────────────────────────────────────────────

    def _on_mode_toggled(self, mode: str):
        if self.callbacks.on_mode_change_request:
            self.callbacks.on_mode_change_request(mode)

    def _on_show_labels_toggled(self, checked: bool):
        if self.canvas.show_labels != checked:
            self.canvas.toggle_labels_visibility()

    @staticmethod
    def _fire(callback):
        if callback:
            callback()
