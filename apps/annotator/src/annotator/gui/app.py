"""Main application window — PySide6 QMainWindow.

Provides the toolbar, menu bar, sidebar splitter, and canvas area.
All user interaction is delegated to the controller via callbacks.
"""

import json
import os
import urllib.request

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCursor,
    QDesktopServices,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QToolBar,
    QToolTip,
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


class ClickableLabel(QLabel):
    """A QLabel that emits a clicked signal on left mouse release and supports hover styling."""

    clicked = Signal()

    def enterEvent(self, event):
        font = self.font()
        font.setUnderline(True)
        self.setFont(font)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        font = self.font()
        font.setUnderline(False)
        self.setFont(font)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class GlobalFocusAndSelectionFilter(QObject):
    """Universal event filter that clears input focus and label text selections
    when clicking outside of them anywhere in the application.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if isinstance(obj, QWidget):
                # 1. Unfocus any active text input widget on outside click
                focused = QApplication.focusWidget()
                if focused and focused.__class__.__name__ in (
                    "QLineEdit",
                    "QTextEdit",
                    "QPlainTextEdit",
                ):
                    if obj != focused:
                        try:
                            if not focused.isAncestorOf(obj):
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
                            if obj != label and not label.isAncestorOf(obj):
                                label.setSelection(0, 0)
            else:
                # obj is not a QWidget (it is a pure QObject)
                focused = QApplication.focusWidget()
                if focused and focused.__class__.__name__ in (
                    "QLineEdit",
                    "QTextEdit",
                    "QPlainTextEdit",
                ):
                    focused.clearFocus()

                main_win = self.parent()
                if main_win:
                    for label in main_win.findChildren(QLabel):
                        if (
                            label.textInteractionFlags()
                            & Qt.TextInteractionFlag.TextSelectableByMouse
                        ):
                            label.setSelection(0, 0)

        return super().eventFilter(obj, event)


class MainAppWindow(QMainWindow):
    """Main application shell providing toolbar, sidebar, and canvas layout.

    All user interactions are delegated to the controller via callback attributes.
    """

    def __init__(
        self, transformer: ViewportTransformer | None = None, port: int = 8000
    ):
        super().__init__()
        self.port = port
        self.api_url = f"http://127.0.0.1:{port}"
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
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self.focus_filter)

        # ── Build UI ──────────────────────────────────────────────
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_area(transformer)
        self._build_status_bar()

    def _build_menu_bar(self):
        menubar = self.menuBar()

        # 1. File Menu
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

        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 2. Edit Menu
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

        # 3. View Menu
        view_menu = menubar.addMenu("&View")

        self.act_fit = QAction("Fit to Screen", self)
        self.act_fit.setShortcut(QKeySequence("F"))
        self.act_fit.setEnabled(False)
        self.act_fit.triggered.connect(lambda: self.canvas.fit_to_screen())
        view_menu.addAction(self.act_fit)

        view_menu.addSeparator()

        self.act_toggle_labels = QAction("Toggle Labels", self)
        self.act_toggle_labels.setShortcut(QKeySequence("T"))
        self.act_toggle_labels.setEnabled(False)
        self.act_toggle_labels.triggered.connect(lambda: self._toggle_labels_action())
        view_menu.addAction(self.act_toggle_labels)

        # 4. Tools Menu
        tools_menu = menubar.addMenu("&Tools")

        self.act_cuts = QAction("Edit Cut Lines…", self)
        self.act_cuts.setShortcut(QKeySequence("Ctrl+L"))
        self.act_cuts.setEnabled(False)
        self.act_cuts.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_cut_editor_request)
        )
        tools_menu.addAction(self.act_cuts)

        self.act_screen_info = QAction("Screen Info…", self)
        self.act_screen_info.setEnabled(False)
        self.act_screen_info.triggered.connect(
            lambda: self._fire(self.callbacks.on_open_screen_info_request)
        )
        tools_menu.addAction(self.act_screen_info)

        # 5. Developer Menu
        dev_menu = menubar.addMenu("&Developer")

        act_swagger = QAction("Open API Docs (Swagger)", self)
        act_swagger.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"{self.api_url}/docs"))
        )
        dev_menu.addAction(act_swagger)

        act_json_state = QAction("View Workspace JSON State", self)
        act_json_state.triggered.connect(self._show_json_state)
        dev_menu.addAction(act_json_state)

        dev_menu.addSeparator()

        act_copy_url = QAction("Copy API Base URL", self)
        act_copy_url.triggered.connect(lambda: self._copy_api_url("#copy"))
        dev_menu.addAction(act_copy_url)

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
        self.chk_show_labels.setChecked(False)
        self.chk_show_labels.setEnabled(False)
        self.chk_show_labels.toggled.connect(self._on_show_labels_toggled)
        tb.addWidget(self.chk_show_labels)

        # Auto Numbering checkbox
        self.chk_auto_number = QCheckBox("Auto Numbering")
        self.chk_auto_number.setToolTip("Toggle Auto Numbering")
        self.chk_auto_number.setChecked(True)
        self.chk_auto_number.setEnabled(False)
        self.chk_auto_number.toggled.connect(self._on_auto_numbering_toggled)
        tb.addWidget(self.chk_auto_number)

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
        self.chk_auto_number.setEnabled(has_img)
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
        self.act_fit.setEnabled(has_img)

        self.act_toggle_labels.setEnabled(has_img)

    def set_mode_str(self, mode: str):
        """Update toolbar mode buttons to match the given mode."""
        action = self._mode_actions.get(mode)
        if action:
            action.setChecked(True)

    def update_status(self, text: str, is_error: bool = False):
        if text.startswith("Workspace:"):
            workspace_id = text.split("Workspace:", 1)[1].strip()
            self.properties.update_status("")  # Remove workspace ID on the right panel
            self.lbl_status_msg.hide()
            self.lbl_workspace_id.setText(workspace_id)
            self.workspace_status_widget.show()
        else:
            self.properties.update_status(text, is_error)
            self.lbl_status_msg.setText(text)
            if is_error:
                self.lbl_status_msg.setStyleSheet("color: #FF6B6B;")
            else:
                self.lbl_status_msg.setStyleSheet("color: #E0E0E0;")
            self.lbl_status_msg.show()
            self.workspace_status_widget.hide()

    def _build_status_bar(self):
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)

        # Left side: general message
        self.lbl_status_msg = QLabel("Ready")
        self.status_bar.addWidget(self.lbl_status_msg)

        # Left side: workspace widgets (grouped in a single widget for consistent layout spacing)
        self.workspace_status_widget = QWidget()
        ws_layout = QHBoxLayout(self.workspace_status_widget)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(6)

        self.lbl_workspace_prefix = QLabel("Workspace:")
        ws_layout.addWidget(self.lbl_workspace_prefix)

        self.lbl_workspace_id = ClickableLabel("")
        self.lbl_workspace_id.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_workspace_id.setToolTip("Click to copy Workspace ID")
        self.lbl_workspace_id.clicked.connect(self._copy_workspace_id_direct)
        ws_layout.addWidget(self.lbl_workspace_id)

        self.workspace_status_widget.hide()
        self.status_bar.addWidget(self.workspace_status_widget)

        # Right side: API indicators
        self.api_status_widget = QWidget()
        api_layout = QHBoxLayout(self.api_status_widget)
        api_layout.setContentsMargins(0, 0, 0, 0)
        api_layout.setSpacing(6)

        # Green indicator dot
        self.lbl_api_dot = QLabel("●")
        self.lbl_api_dot.setStyleSheet(
            "color: #2ECC71; font-size: 10pt; font-family: Arial;"
        )

        # Static API prefix label (non-clickable)
        self.lbl_api_prefix = QLabel("API:")

        # Clickable API link (only the actual URL, click to copy URL, no tooltip)
        self.lbl_api_link = ClickableLabel(self.api_url)
        self.lbl_api_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_api_link.setToolTip("Click to copy API URL")
        self.lbl_api_link.clicked.connect(self._copy_api_url_direct)

        # Docs link (clickable)
        self.lbl_docs_link = QLabel(
            f"<a href='{self.api_url}/docs' style='color: #18A0FB; text-decoration: none;'>[API Docs]</a>"
        )
        self.lbl_docs_link.setOpenExternalLinks(True)

        api_layout.addWidget(self.lbl_api_dot)
        api_layout.addWidget(self.lbl_api_prefix)
        api_layout.addWidget(self.lbl_api_link)
        api_layout.addWidget(self.lbl_docs_link)

        self.status_bar.addPermanentWidget(self.api_status_widget)

    def _copy_api_url(self, link):
        if link == "#copy":
            self._copy_api_url_direct()

    def _copy_api_url_direct(self):
        QApplication.clipboard().setText(self.api_url)
        # Show a popup bubble at the mouse cursor position
        QToolTip.showText(QCursor.pos(), "Copied!", self.lbl_api_link)

    def _copy_workspace_id_direct(self):
        ws_id = self.lbl_workspace_id.text()
        if ws_id:
            QApplication.clipboard().setText(ws_id)
            # Show a popup bubble at the mouse cursor position
            QToolTip.showText(QCursor.pos(), "Copied!", self.lbl_workspace_id)

    def _show_json_state(self):
        try:
            req = urllib.request.Request(f"{self.api_url}/workspace/state")
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                formatted_json = json.dumps(data, indent=2)
        except Exception as e:
            formatted_json = f"Failed to fetch JSON state:\n{e}"

        dialog = QDialog(self, Qt.WindowType.Tool)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("Workspace JSON State")
        dialog.resize(600, 600)

        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(formatted_json)

        font = text_edit.font()
        font.setFamily("Courier")
        text_edit.setFont(font)

        layout.addWidget(text_edit)
        dialog.show()

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

    def _on_auto_numbering_toggled(self, checked: bool):
        if self.callbacks.on_toggle_auto_numbering_request:
            self.callbacks.on_toggle_auto_numbering_request(checked)

    def _toggle_labels_action(self):
        self.canvas.toggle_labels_visibility()
        if hasattr(self, "chk_show_labels"):
            self.chk_show_labels.setChecked(self.canvas.show_labels)

    @staticmethod
    def _fire(callback):
        if callback:
            callback()
