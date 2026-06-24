"""Cut line editor dialog — Qt rewrite.

Modal dialog for editing horizontal cut lines on the full screenshot.
Uses a QWidget with QPainter for the canvas and a QListWidget for the
coordinate list.
"""

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from annotator.models import Component

from .design_system import (
    ColorSystem,
    LayoutTokens,
    get_caption_font,
    get_header_font,
    set_widget_text_color,
)
from .image_utils import pil_to_qpixmap
from .validation import CutValidator

MIN_CUT_GAP = 50
SNAP_DISTANCE = 8


class _CutCanvasWidget(QWidget):
    """Internal canvas widget for the cut editor.

    Stores a full-resolution QPixmap of the source image and uses QPainter
    for zoom/scroll transforms and component overlay rectangles, avoiding
    PIL resize and RGBA compositing per frame.
    """

    def __init__(self, dialog: CutEditorDialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._base_pixmap: QPixmap | None = None
        self.zoom_factor: float = 1.0
        self._scroll_offset: float = 0.0

    def _to_canvas_y(self, img_y: int) -> float:
        return img_y * self.zoom_factor - self._scroll_offset

    def _to_img_y(self, canvas_y: float) -> int:
        return round((canvas_y + self._scroll_offset) / self.zoom_factor)

    def fit_and_render(self):
        """Compute zoom and build the base QPixmap from the source image."""
        if not self.dialog.source_image:
            return
        vw = self.width()
        if vw <= 1:
            vw = 700
        img_w = self.dialog.source_image.width
        self.zoom_factor = max(0.05, min(1.0, (vw - 20) / img_w))
        self._base_pixmap = pil_to_qpixmap(self.dialog.source_image)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        palette = self.palette()
        p.fillRect(self.rect(), palette.color(QPalette.ColorRole.Window))

        if not self._base_pixmap:
            p.end()
            return

        zoom = self.zoom_factor
        src_w = self._base_pixmap.width()
        src_h = self._base_pixmap.height()

        # Draw the source image scaled by zoom, offset by scroll
        target = QRectF(0, -self._scroll_offset, src_w * zoom, src_h * zoom)
        source = QRectF(0, 0, src_w, src_h)
        p.drawPixmap(target, self._base_pixmap, source)

        # Draw semi-transparent overlays for existing components
        comp_outline_pen = QPen(ColorSystem.get_cut_comp_outline(), 1)
        comp_fill_brush = ColorSystem.get_cut_comp_fill()
        for comp in self.dialog.existing_components:
            cx1 = comp.bounds.left * zoom
            cy1 = self._to_canvas_y(comp.bounds.top)
            cx2 = comp.bounds.right * zoom
            cy2 = self._to_canvas_y(comp.bounds.bottom)
            rect = QRectF(cx1, cy1, cx2 - cx1, cy2 - cy1)
            p.fillRect(rect, comp_fill_brush)
            p.setPen(comp_outline_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)

        # Draw cut lines
        disp_w = src_w * zoom
        for i, y in enumerate(self.dialog.cut_lines):
            cy = self._to_canvas_y(y)
            is_selected = i == self.dialog.selected_index
            color = (
                palette.color(QPalette.ColorRole.Highlight)
                if is_selected
                else QColor(ColorSystem.ERROR)
            )
            width = 3 if is_selected else 2

            pen = QPen(color, width, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(0, cy), QPointF(disp_w, cy))

            label_font = get_caption_font()
            label_font.setBold(True)
            p.setFont(label_font)
            p.setPen(QPen(color))
            p.drawText(QPointF(disp_w - 50, cy - 6), f"Y={y}")

        p.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        canvas_y = event.position().y()
        img_y = self._to_img_y(canvas_y)

        if self.dialog.mode == "adding":
            intersecting = CutValidator.get_intersecting_component(
                img_y, self.dialog.existing_components
            )
            if intersecting:
                self.dialog.status_label.setText(
                    f"Blocked: intersects component '{intersecting.label}'"
                )
                return

            if CutValidator.is_valid_position(
                img_y,
                self.dialog.source_image.height,
                self.dialog.cut_lines,
                MIN_CUT_GAP,
            ):
                self.dialog.cut_lines.append(img_y)
                self.dialog.cut_lines.sort()
                self.dialog.selected_index = self.dialog.cut_lines.index(img_y)
                self.dialog.cancel_add_mode()
                self.update()
                self.dialog.refresh_listbox()
            else:
                self.dialog.status_label.setText(
                    "Blocked: invalid gap to adjacent cuts"
                )
            return

        hit_index = self._hit_test_cut(canvas_y)
        if hit_index >= 0:
            self.dialog.selected_index = hit_index
            self.dialog.mode = "dragging"
            self.dialog.drag_index = hit_index
            self.dialog.drag_start_y = img_y
            self.dialog.last_valid_drag_y = self.dialog.cut_lines[hit_index]
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.dialog.selected_index = -1

        self.update()
        self.dialog.refresh_listbox()

    def mouseMoveEvent(self, event: QMouseEvent):
        canvas_y = event.position().y()

        if self.dialog.mode == "dragging" and self.dialog.drag_index >= 0:
            new_y = self._to_img_y(canvas_y)
            new_y = max(
                MIN_CUT_GAP, min(self.dialog.source_image.height - MIN_CUT_GAP, new_y)
            )

            intersecting = CutValidator.get_intersecting_component(
                new_y, self.dialog.existing_components
            )
            if intersecting:
                self.dialog.status_label.setText(
                    f"Blocked: intersects component '{intersecting.label}'"
                )
                new_y = self.dialog.last_valid_drag_y
            else:
                self.dialog.status_label.setText("")

            if CutValidator.is_valid_position_for_drag(
                new_y,
                self.dialog.source_image.height,
                self.dialog.cut_lines,
                self.dialog.drag_index,
                MIN_CUT_GAP,
            ):
                self.dialog.cut_lines[self.dialog.drag_index] = new_y
                self.dialog.cut_lines.sort()
                self.dialog.drag_index = self.dialog.cut_lines.index(new_y)
                self.dialog.selected_index = self.dialog.drag_index
                self.dialog.last_valid_drag_y = new_y
            else:
                self.dialog.cut_lines[self.dialog.drag_index] = (
                    self.dialog.last_valid_drag_y
                )

            self.update()
            self.dialog.refresh_listbox()
            return

        if self.dialog.mode == "adding":
            return

        hit = self._hit_test_cut(canvas_y)
        if hit >= 0:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.dialog.mode == "dragging":
            self.dialog.mode = "idle"
            self.dialog.drag_index = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent):
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            self._scroll_offset -= pixel_delta.y()
        else:
            angle = event.angleDelta().y()
            self._scroll_offset -= angle / 2.0

        # Clamp scroll based on the scaled image height
        if self._base_pixmap:
            scaled_h = self._base_pixmap.height() * self.zoom_factor
            max_scroll = max(0, scaled_h - self.height())
            self._scroll_offset = max(0, min(max_scroll, self._scroll_offset))
        else:
            self._scroll_offset = max(0, self._scroll_offset)

        self.update()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_and_render()

    def _hit_test_cut(self, canvas_y: float) -> int:
        for i, y in enumerate(self.dialog.cut_lines):
            cy = self._to_canvas_y(y)
            if abs(canvas_y - cy) <= SNAP_DISTANCE:
                return i
        return -1


class CutEditorDialog(QDialog):
    """Modal dialog for editing horizontal cut lines on the full screenshot."""

    def __init__(
        self,
        parent,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Cut Lines")
        self.resize(900, 700)
        self.setModal(True)

        self.source_image = image
        self.cut_lines: list[int] = sorted(initial_cuts)
        self.existing_components = components
        self.cut_lines_result: list[int] | None = None

        # Interaction state
        self.mode: str = "idle"
        self.drag_index: int = -1
        self.drag_start_y: int = 0
        self.last_valid_drag_y: int = 0
        self.selected_index: int = -1

        self._build_ui()

        # Initial render after layout settles
        QTimer.singleShot(50, self.canvas_widget.fit_and_render)
        self.refresh_listbox()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Left: canvas
        self.canvas_widget = _CutCanvasWidget(self)
        layout.addWidget(self.canvas_widget, stretch=3)

        # Right: controls
        right = QWidget()
        right.setFixedWidth(200)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(
            LayoutTokens.MARGIN_DEFAULT,
            LayoutTokens.MARGIN_DEFAULT,
            LayoutTokens.MARGIN_DEFAULT,
            LayoutTokens.MARGIN_DEFAULT,
        )

        lbl = QLabel("CUT LINES")
        lbl.setFont(get_header_font())
        right_layout.addWidget(lbl)

        self.listbox = QListWidget()
        self.listbox.currentRowChanged.connect(self._on_listbox_select)
        right_layout.addWidget(self.listbox, stretch=1)

        # Action buttons
        self.btn_add = QPushButton("Add Cut")
        self.btn_add.clicked.connect(self._start_add_mode)
        right_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setEnabled(False)
        self.btn_remove.clicked.connect(self._remove_selected)
        right_layout.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_all)
        right_layout.addWidget(self.btn_clear)

        self.status_label = QLabel("")
        self.status_label.setFont(get_caption_font())
        set_widget_text_color(self.status_label, ColorSystem.ERROR)
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        right_layout.addStretch()

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.setFixedWidth(80)
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_ok)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(btn_cancel)
        right_layout.addLayout(btn_row)

        layout.addWidget(right)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.mode == "adding":
                self.cancel_add_mode()
            else:
                self._on_cancel()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._remove_selected()
            return
        super().keyPressEvent(event)

    def _start_add_mode(self):
        self.mode = "adding"
        self.canvas_widget.setCursor(Qt.CursorShape.CrossCursor)
        self.status_label.setText(
            "Click to add a horizontal cut line. Escape to cancel."
        )
        self.btn_add.setEnabled(False)

    def cancel_add_mode(self):
        self.mode = "idle"
        self.canvas_widget.setCursor(Qt.CursorShape.ArrowCursor)
        self.status_label.setText("")
        self.btn_add.setEnabled(True)

    def refresh_listbox(self):
        self.listbox.blockSignals(True)
        self.listbox.clear()
        for i, y in enumerate(self.cut_lines):
            self.listbox.addItem(f"Cut {i + 1}:  Y = {y}")

        if 0 <= self.selected_index < len(self.cut_lines):
            self.listbox.setCurrentRow(self.selected_index)
        self.listbox.blockSignals(False)

        self.btn_remove.setEnabled(0 <= self.selected_index < len(self.cut_lines))

    def _on_listbox_select(self, row):
        self.selected_index = row
        self.canvas_widget.update()
        self.btn_remove.setEnabled(0 <= self.selected_index < len(self.cut_lines))

    def _remove_selected(self):
        if 0 <= self.selected_index < len(self.cut_lines):
            self.cut_lines.pop(self.selected_index)
            self.selected_index = min(self.selected_index, len(self.cut_lines) - 1)
            self.canvas_widget.update()
            self.refresh_listbox()

    def _clear_all(self):
        if not self.cut_lines:
            return
        self.cut_lines.clear()
        self.selected_index = -1
        self.canvas_widget.update()
        self.refresh_listbox()

    def _on_ok(self):
        self.cut_lines_result = sorted(self.cut_lines)
        self.accept()

    def _on_cancel(self):
        self.cut_lines_result = None
        self.reject()
