"""Dark-mode theming for the PySide6 application.

Provides a dark QPalette using the Fusion style and a supplementary QSS
stylesheet for fine-tuned widget styling.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ── Colour Tokens ─────────────────────────────────────────────────────

WINDOW_BG = QColor("#1e1e1e")
BASE_BG = QColor("#121212")
ALT_BASE = QColor("#2b2b2b")
INPUT_BG = QColor("#2b2b2b")
BORDER = QColor("#3c3c3c")
TEXT_PRIMARY = QColor("#e0e0e0")
TEXT_SECONDARY = QColor("#888888")
TEXT_DISABLED = QColor("#555555")
ACCENT = QColor("#0c8ce9")
ACCENT_LIGHT = QColor("#3aa5f0")
ERROR = QColor("#e74c3c")
BOX_RED = QColor("#ff4444")
BUTTON_BG = QColor("#2b2b2b")
BUTTON_HOVER = QColor("#363636")
TOOLTIP_BG = QColor("#2d2d2d")
TOOLTIP_FG = QColor("#d0d0d0")


def build_dark_palette() -> QPalette:
    """Construct a dark QPalette matching the existing annotator colour scheme."""
    p = QPalette()

    p.setColor(QPalette.ColorRole.Window, WINDOW_BG)
    p.setColor(QPalette.ColorRole.WindowText, TEXT_PRIMARY)
    p.setColor(QPalette.ColorRole.Base, INPUT_BG)
    p.setColor(QPalette.ColorRole.AlternateBase, ALT_BASE)
    p.setColor(QPalette.ColorRole.Text, TEXT_PRIMARY)
    p.setColor(QPalette.ColorRole.Button, BUTTON_BG)
    p.setColor(QPalette.ColorRole.ButtonText, TEXT_PRIMARY)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Link, ACCENT)
    p.setColor(QPalette.ColorRole.LinkVisited, ACCENT_LIGHT)
    p.setColor(QPalette.ColorRole.ToolTipBase, TOOLTIP_BG)
    p.setColor(QPalette.ColorRole.ToolTipText, TOOLTIP_FG)

    # Disabled colours
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, TEXT_DISABLED)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, TEXT_DISABLED)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, TEXT_DISABLED)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#444444"))

    return p


# ── QSS Stylesheet ───────────────────────────────────────────────────

_STYLESHEET = """
QMainWindow {
    background-color: #1e1e1e;
}

QToolBar {
    background-color: #252525;
    border-bottom: 1px solid #3c3c3c;
    spacing: 4px;
    padding: 4px;
}

QToolBar QToolButton {
    color: #e0e0e0;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 8px;
}

QToolBar QToolButton:hover {
    background-color: #363636;
    border-color: #4a4a4a;
}

QToolBar QToolButton:checked {
    background-color: #0c8ce9;
    color: white;
}

QToolBar QToolButton:disabled {
    color: #555555;
}

QToolBar QLabel {
    color: #888888;
}

QSplitter::handle {
    background-color: #3c3c3c;
    width: 1px;
}

QTreeView {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: none;
    outline: none;
    selection-background-color: #0c8ce9;
    selection-color: white;
}

QTreeView::item {
    padding: 3px 4px;
}

QTreeView::item:hover {
    background-color: #2a2a2a;
}

QTreeView::item:selected {
    background-color: #0c8ce9;
    color: white;
}

QTreeView::branch:has-children:closed {
    image: none;
    border-image: none;
}

QTreeView::branch:has-children:open {
    image: none;
    border-image: none;
}

QScrollBar:vertical {
    background: #1e1e1e;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #3c3c3c;
    min-height: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #1e1e1e;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #3c3c3c;
    min-width: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background: #555555;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #2b2b2b;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 3px 5px;
    selection-background-color: #0c8ce9;
    selection-color: white;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #0c8ce9;
}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #1a1a1a;
    color: #555555;
    border-color: #2c2c2c;
}

QLineEdit:read-only {
    background-color: #222222;
    color: #aaaaaa;
}

QCheckBox {
    color: #e0e0e0;
    spacing: 6px;
}

QCheckBox:disabled {
    color: #555555;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 2px;
    background-color: #2b2b2b;
}

QCheckBox::indicator:checked {
    background-color: #0c8ce9;
    border-color: #0c8ce9;
}

QCheckBox::indicator:disabled {
    background-color: #1a1a1a;
    border-color: #333333;
}

QPushButton {
    background-color: #2b2b2b;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 15px;
    min-width: 60px;
}

QPushButton:hover {
    background-color: #363636;
    border-color: #4a4a4a;
}

QPushButton:pressed {
    background-color: #0c8ce9;
    color: white;
}

QPushButton:disabled {
    background-color: #1a1a1a;
    color: #555555;
    border-color: #2c2c2c;
}

QMenuBar {
    background-color: #252525;
    color: #e0e0e0;
    border-bottom: 1px solid #3c3c3c;
}

QMenuBar::item:selected {
    background-color: #363636;
}

QMenu {
    background-color: #252525;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
}

QMenu::item:selected {
    background-color: #0c8ce9;
    color: white;
}

QMenu::separator {
    height: 1px;
    background: #3c3c3c;
    margin: 4px 8px;
}

QListWidget {
    background-color: #2b2b2b;
    color: #ffffff;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    outline: none;
}

QListWidget::item {
    padding: 3px 6px;
}

QListWidget::item:selected {
    background-color: #0c8ce9;
    color: white;
}

QListWidget::item:hover {
    background-color: #333333;
}

QDialog {
    background-color: #1e1e1e;
}

QLabel {
    color: #e0e0e0;
}

QLabel[secondary="true"] {
    color: #888888;
}

QLabel[error="true"] {
    color: #e74c3c;
}

QGroupBox {
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    padding: 0 6px;
}

QComboBox {
    background-color: #2b2b2b;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 3px 8px;
}

QComboBox:hover {
    border-color: #4a4a4a;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2b2b2b;
    color: #e0e0e0;
    selection-background-color: #0c8ce9;
    selection-color: white;
    border: 1px solid #3c3c3c;
}

QProgressBar {
    background-color: #2b2b2b;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    text-align: center;
    color: #e0e0e0;
}

QProgressBar::chunk {
    background-color: #0c8ce9;
    border-radius: 2px;
}
"""


def apply_dark_theme(app: QApplication) -> None:
    """Apply the dark theme palette and stylesheet to the application."""
    app.setStyle("Fusion")
    app.setPalette(build_dark_palette())
    app.setStyleSheet(_STYLESHEET)
