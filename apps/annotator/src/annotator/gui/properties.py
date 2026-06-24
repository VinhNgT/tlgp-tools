from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    MARGIN,
    SPACING_SM,
    colors,
    get_caption_font,
    get_header_font,
    set_widget_text_color,
)


class CornerSelector(QWidget):
    corner_selected = Signal(str)

    def __init__(self, on_corner_selected_callback=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self._on_corner_selected = on_corner_selected_callback
        self.selected_corner = "top_left"
        self.enabled = True
        self.setMouseTracking(True)

        self.x1, self.y1 = 10, 10
        self.x2, self.y2 = 54, 54

        self.corners = {
            "top_left": (self.x1, self.y1),
            "top_right": (self.x2, self.y1),
            "bottom_left": (self.x1, self.y2),
            "bottom_right": (self.x2, self.y2),
        }

        if on_corner_selected_callback:
            self.corner_selected.connect(on_corner_selected_callback)

    def set_corner(self, corner: str):
        if corner in self.corners:
            self.selected_corner = corner
            self.update()

    def set_state(self, state: str):
        self.enabled = state != "disabled"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = self.palette()
        cg = (
            QPalette.ColorGroup.Active if self.enabled else QPalette.ColorGroup.Disabled
        )

        bg = palette.color(cg, QPalette.ColorRole.Window)
        border = palette.color(cg, QPalette.ColorRole.Mid)

        # Background
        p.fillRect(self.rect(), bg)
        p.setPen(QPen(border, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Dashed rectangle
        outline_color = palette.color(cg, QPalette.ColorRole.Dark)
        pen = QPen(outline_color, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1)

        # Crosshairs
        cx = (self.x1 + self.x2) // 2
        cy = (self.y1 + self.y2) // 2
        line_color = palette.color(cg, QPalette.ColorRole.Midlight)
        pen = QPen(line_color, 1, Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.drawLine(self.x1, cy, self.x2, cy)
        p.drawLine(cx, self.y1, cx, self.y2)

        # Corner dots
        r = 5
        for name, (px, py) in self.corners.items():
            if self.enabled and self.selected_corner == name:
                p.setPen(QPen(Qt.GlobalColor.white, 1.5))
                p.setBrush(palette.color(QPalette.ColorRole.Highlight))
            else:
                dot_fill = palette.color(cg, QPalette.ColorRole.Button)
                dot_outline = palette.color(cg, QPalette.ColorRole.Dark)
                p.setPen(QPen(dot_outline, 1))
                p.setBrush(dot_fill)
            p.drawEllipse(px - r, py - r, r * 2, r * 2)

        p.end()

    def _get_closest_corner(self, mx: int, my: int) -> str | None:
        best_corner = None
        min_dist = 18.0
        for name, (cx, cy) in self.corners.items():
            dist = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                best_corner = name
        return best_corner

    def mousePressEvent(self, event):
        if not self.enabled:
            return
        clicked = self._get_closest_corner(
            int(event.position().x()), int(event.position().y())
        )
        if clicked:
            self.set_corner(clicked)
            self.corner_selected.emit(clicked)

    def mouseMoveEvent(self, event):
        if not self.enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        hovered = self._get_closest_corner(
            int(event.position().x()), int(event.position().y())
        )
        if hovered:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)


class ComponentPropertiesView(QWidget):
    """Metadata editor properties panel. Fires changes to the controller via callbacks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_property_changed = None
        self.on_focus_changed = None
        self._text_focused = False

        self._selected_box_id = None
        self._current_label = ""
        self._current_is_visible = True
        self._current_is_locked = False
        self._current_pill_corner = "top_left"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            MARGIN,
            MARGIN,
            MARGIN,
            MARGIN,
        )

        lbl_header = QLabel("PROPERTIES")
        lbl_header.setFont(get_header_font())
        layout.addWidget(lbl_header)

        # Name field
        name_row = QHBoxLayout()
        lbl_name = QLabel("Name:")
        lbl_name.setFixedWidth(50)
        name_row.addWidget(lbl_name)

        self.entry_name = QLineEdit()
        self.entry_name.returnPressed.connect(self._save_name)
        self.entry_name.editingFinished.connect(self._save_name)
        name_row.addWidget(self.entry_name)
        layout.addLayout(name_row)

        # Coordinate fields
        coords_grid = QGridLayout()
        coords_grid.setSpacing(SPACING_SM)
        self.prop_entries: dict[str, QLineEdit] = {}
        for idx, (label, key) in enumerate(
            [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]
        ):
            row = idx // 2
            col = (idx % 2) * 2
            lbl = QLabel(label)
            lbl.setFixedWidth(20)
            lbl_font = get_caption_font()
            lbl_font.setBold(True)
            lbl.setFont(lbl_font)
            coords_grid.addWidget(lbl, row, col)

            entry = QLineEdit()
            entry.setFixedWidth(70)
            entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            entry.setReadOnly(True)
            coords_grid.addWidget(entry, row, col + 1)
            self.prop_entries[key] = entry

        layout.addLayout(coords_grid)

        # Visibility controls
        vis_row = QHBoxLayout()
        self.chk_visible = QCheckBox("Visible")
        self.chk_visible.setChecked(True)
        self.chk_visible.stateChanged.connect(self._save_visibility)
        vis_row.addWidget(self.chk_visible)

        self.chk_locked = QCheckBox("Locked")
        self.chk_locked.setChecked(False)
        self.chk_locked.stateChanged.connect(self._save_visibility)
        vis_row.addWidget(self.chk_locked)
        vis_row.addStretch()
        layout.addLayout(vis_row)

        # Pill corner selector
        pill_row = QHBoxLayout()
        lbl_pill = QLabel("Pill Corner:")
        pill_row.addWidget(lbl_pill)

        self.corner_selector = CornerSelector(
            on_corner_selected_callback=self._save_corner
        )
        pill_row.addWidget(self.corner_selector)
        pill_row.addStretch()
        layout.addLayout(pill_row)

        layout.addStretch()

        # Status text at the bottom
        self.txt_status = QLabel("Connecting...")
        self.txt_status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        self.txt_status.setFont(get_caption_font())
        set_widget_text_color(self.txt_status, colors.muted)
        self.txt_status.setWordWrap(True)
        layout.addWidget(self.txt_status)

        # Track focus changes
        self.entry_name.installEventFilter(self)
        for entry in self.prop_entries.values():
            entry.installEventFilter(self)

        self.disable_properties_fields()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn:
            if isinstance(obj, (QLineEdit, QTextEdit)):
                self._on_focus_in()
        elif event.type() == QEvent.Type.FocusOut:
            self._on_focus_out()
        return super().eventFilter(obj, event)

    def update_status(self, text: str, is_error: bool = False):
        self.txt_status.setText(text)
        color = colors.error if is_error else colors.muted
        set_widget_text_color(self.txt_status, color)

    def update_properties_panel(
        self,
        box_id: str,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        is_visible: bool,
        is_locked: bool,
        is_effectively_locked: bool,
        pill_corner: str,
    ):
        if self._selected_box_id and self._selected_box_id != box_id:
            self._save_name()

        self._selected_box_id = box_id
        self._current_label = label
        self._current_is_visible = is_visible
        self._current_is_locked = is_locked
        self._current_pill_corner = pill_corner

        self.chk_visible.setEnabled(True)
        self.chk_locked.setEnabled(True)

        # Block signals during programmatic update
        self.chk_visible.blockSignals(True)
        self.chk_locked.blockSignals(True)
        self.chk_visible.setChecked(is_visible)
        self.chk_locked.setChecked(is_locked)
        self.chk_visible.blockSignals(False)
        self.chk_locked.blockSignals(False)

        is_editable = not is_effectively_locked

        self.entry_name.setEnabled(is_editable)
        for entry in self.prop_entries.values():
            entry.setEnabled(True)
            entry.setReadOnly(True)

        self.corner_selector.set_state("normal" if is_editable else "disabled")
        self.corner_selector.set_corner(pill_corner)

    def is_field_focused(self, field_name: str) -> bool:
        """Returns True if the specified field currently has keyboard focus."""
        focused = self.focusWidget()
        if field_name == "name":
            return focused == self.entry_name
        elif field_name in self.prop_entries:
            return focused == self.prop_entries[field_name]
        return False

    def update_field_value(self, field_name: str, value: str):
        """Updates the text content of a properties field if it is not disabled."""
        if field_name == "name":
            if self.entry_name.isEnabled():
                self.entry_name.setText(value)
        elif field_name in self.prop_entries:
            entry = self.prop_entries[field_name]
            if entry.isEnabled():
                entry.setReadOnly(False)
                entry.setText(value)
                entry.setReadOnly(True)

    def disable_properties_fields(self):
        if self._selected_box_id:
            self._save_name()
        self._selected_box_id = None
        self._current_label = ""
        self._current_is_visible = True
        self._current_is_locked = False
        self._current_pill_corner = "top_left"
        self.entry_name.clear()
        self.entry_name.setEnabled(False)
        for entry in self.prop_entries.values():
            entry.setReadOnly(False)
            entry.clear()
            entry.setEnabled(False)

        self.corner_selector.set_state("disabled")
        self.chk_visible.setEnabled(False)
        self.chk_locked.setEnabled(False)

    def is_text_focused(self) -> bool:
        return self._text_focused

    def _on_focus_in(self):
        if not self._text_focused:
            self._text_focused = True
            if self.on_focus_changed:
                self.on_focus_changed(True)

    def _on_focus_out(self):
        QTimer.singleShot(50, self._check_focus_still_on_text)

    def _check_focus_still_on_text(self):
        focused = self.focusWidget()
        still_focused = isinstance(focused, (QLineEdit, QTextEdit))
        if self._text_focused != still_focused:
            self._text_focused = still_focused
            if self.on_focus_changed:
                self.on_focus_changed(still_focused)

    def _save_name(self):
        if self._selected_box_id and self.on_property_changed:
            val = self.entry_name.text().strip()
            if val and val != self._current_label:
                self._current_label = val
                self.on_property_changed(self._selected_box_id, label=val)

    def _save_visibility(self):
        if self._selected_box_id and self.on_property_changed:
            visible = self.chk_visible.isChecked()
            locked = self.chk_locked.isChecked()
            if visible != self._current_is_visible or locked != self._current_is_locked:
                self.on_property_changed(
                    self._selected_box_id,
                    visibility={"visible": visible, "locked": locked},
                )

    def _save_corner(self, corner: str):
        if self._selected_box_id and self.on_property_changed:
            if corner != self._current_pill_corner:
                self.on_property_changed(
                    self._selected_box_id, style={"pillCorner": corner}
                )
