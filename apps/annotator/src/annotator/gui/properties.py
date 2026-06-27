"""Property inspector panel for editing component metadata and API tables."""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CornerSelector(QWidget):
    corner_selected = Signal(str)

    def __init__(self, on_corner_selected_callback=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self._on_corner_selected = on_corner_selected_callback
        self.selected_corner: str | None = "top_left"
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

    def set_corner(self, corner: str | None):
        if corner is None or corner in self.corners:
            self.selected_corner = corner
            self.update()

    def set_state(self, state: str):
        self.enabled = state != "disabled"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.enabled:
            bg = QColor("#1E1E1E")
            border = QColor("#5A5A5C")
            dashed_rect_color = QColor("#8C8C8C")
            crosshairs_color = QColor("#4F4F4F")
        else:
            bg = QColor("#222223")
            border = QColor("#383839")
            dashed_rect_color = QColor("#505052")
            crosshairs_color = QColor("#38383A")

        # Background
        p.fillRect(self.rect(), bg)
        p.setPen(QPen(border, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Dashed rectangle
        pen = QPen(dashed_rect_color, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1)

        # Crosshairs
        cx = (self.x1 + self.x2) // 2
        cy = (self.y1 + self.y2) // 2
        pen = QPen(crosshairs_color, 1, Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.drawLine(self.x1, cy, self.x2, cy)
        p.drawLine(cx, self.y1, cx, self.y2)

        # Corner dots
        r = 5
        for name, (px, py) in self.corners.items():
            if self.enabled:
                if self.selected_corner == name:
                    # Active selected dot: Figma blue with white border
                    p.setPen(QPen(QColor("#FFFFFF"), 1.5))
                    p.setBrush(QColor("#18A0FB"))
                else:
                    # Active unselected dot: dark gray fill with subtle border
                    p.setPen(QPen(QColor("#8C8C8C"), 1))
                    p.setBrush(QColor("#2C2D2E"))
            else:
                if self.selected_corner == name:
                    # Disabled selected dot: muted highlight color (medium gray) with darker border
                    p.setPen(QPen(QColor("#303030"), 1.5))
                    p.setBrush(QColor("#707070"))
                else:
                    # Disabled unselected dot: muted gray fill and border
                    p.setPen(QPen(QColor("#444444"), 1))
                    p.setBrush(QColor("#2C2D2E"))
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
        self._current_pill_corner: str | None = "top_left"
        self._current_number = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl_header = QLabel("PROPERTIES")
        header_font = lbl_header.font()
        header_font.setBold(True)
        header_font.setPointSize(9)
        lbl_header.setFont(header_font)
        lbl_header.setStyleSheet("color: #B0B0B0; padding-bottom: 4px;")
        layout.addWidget(lbl_header)

        # Name field
        name_row = QHBoxLayout()
        lbl_name = QLabel("Name")
        lbl_name.setFixedWidth(50)
        lbl_name.setStyleSheet("color: #C5C5C5;")
        name_row.addWidget(lbl_name)

        self.entry_name = QLineEdit()
        self.entry_name.returnPressed.connect(self._save_name)
        self.entry_name.editingFinished.connect(self._save_name)
        name_row.addWidget(self.entry_name)
        layout.addLayout(name_row)

        # Number field
        number_row = QHBoxLayout()
        lbl_number = QLabel("Number")
        lbl_number.setFixedWidth(50)
        lbl_number.setStyleSheet("color: #C5C5C5;")
        number_row.addWidget(lbl_number)

        self.entry_number = QLineEdit()
        self.entry_number.setReadOnly(True)
        number_row.addWidget(self.entry_number)
        layout.addLayout(number_row)

        # Coordinate fields
        coords_grid = QGridLayout()
        coords_grid.setSpacing(8)
        self.prop_entries: dict[str, QLineEdit] = {}
        for idx, (label, key) in enumerate(
            [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]
        ):
            row = idx // 2
            col = (idx % 2) * 2

            # Label
            lbl = QLabel(label)
            lbl.setFixedWidth(20)
            lbl.setStyleSheet("color: #C5C5C5;")
            coords_grid.addWidget(lbl, row, col)

            # Input
            entry = QLineEdit()
            entry.setFixedWidth(70)
            entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
            entry.setReadOnly(True)
            coords_grid.addWidget(entry, row, col + 1)
            self.prop_entries[key] = entry

        layout.addLayout(coords_grid)

        # Pill corner selector
        pill_row = QHBoxLayout()
        lbl_pill = QLabel("Pill Corner:")
        lbl_pill.setStyleSheet("color: #C5C5C5;")
        pill_row.addWidget(lbl_pill)

        self.corner_selector = CornerSelector(
            on_corner_selected_callback=self._save_corner
        )
        pill_row.addWidget(self.corner_selector)
        pill_row.addStretch()
        layout.addLayout(pill_row)

        layout.addStretch()

        # Status text at the bottom
        self.txt_status = QLabel("")
        self.txt_status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        self.txt_status.setWordWrap(True)
        self.txt_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.txt_status)

        # Track focus changes
        self.entry_name.installEventFilter(self)
        self.entry_number.installEventFilter(self)
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
        if is_error:
            self.txt_status.setStyleSheet("color: #FF6B6B;")
        else:
            self.txt_status.setStyleSheet("color: rgba(165, 165, 165, 0.4);")

    def update_properties_panel(
        self,
        box_id: str,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        pill_corner: str,
        number: str,
    ):
        if self._selected_box_id and self._selected_box_id != box_id:
            self._save_name()

        self._selected_box_id = box_id
        self._current_label = label
        self._current_pill_corner = pill_corner
        self._current_number = number

        self.entry_name.setEnabled(True)
        self.entry_number.setEnabled(True)
        self.entry_number.setReadOnly(True)
        self.entry_number.setStyleSheet("color: #8C8C8C; background-color: #2D2D30;")

        for entry in self.prop_entries.values():
            entry.setEnabled(True)
            entry.setReadOnly(True)

        self.corner_selector.set_state("normal")
        self.corner_selector.set_corner(pill_corner)

    def is_field_focused(self, field_name: str) -> bool:
        """Returns True if the specified field currently has keyboard focus."""
        focused = self.focusWidget()
        if field_name == "name":
            return focused == self.entry_name
        elif field_name == "number":
            return focused == self.entry_number
        elif field_name in self.prop_entries:
            return focused == self.prop_entries[field_name]
        return False

    def update_field_value(self, field_name: str, value: str):
        """Updates the text content of a properties field if it is not disabled."""
        if field_name == "name":
            if self.entry_name.isEnabled():
                self.entry_name.setText(value)
        elif field_name == "number":
            if self.entry_number.isEnabled():
                self.entry_number.setText(value)
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
        self._current_pill_corner = None
        self._current_number = ""
        self.entry_name.setEnabled(False)
        self.entry_name.clear()
        self.entry_number.setEnabled(False)
        self.entry_number.clear()
        self.entry_number.setStyleSheet("")
        for entry in self.prop_entries.values():
            entry.setEnabled(False)
            entry.clear()

        self.corner_selector.set_state("disabled")
        self.corner_selector.set_corner(None)

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



    def _save_corner(self, corner: str):
        if self._selected_box_id and self.on_property_changed:
            if corner != self._current_pill_corner:
                self.on_property_changed(self._selected_box_id, pillCorner=corner)
