"""Central design system for the annotator application.

Defines semantic design tokens, overlay colors, and platform-agnostic
font helpers to ensure consistency and seamless light/dark mode support.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


def _get_qapp() -> QApplication | None:
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else None


class ColorSystem:
    @staticmethod
    def is_dark_mode() -> bool:
        app = _get_qapp()
        if not app:
            return False
        palette = app.palette()
        bg_color = palette.color(QPalette.ColorRole.Window)
        return bg_color.lightness() < 128

    @classmethod
    def get_muted(cls) -> str:
        app = _get_qapp()
        if not app:
            return "#888888"
        return app.palette().color(QPalette.ColorRole.PlaceholderText).name()

    # Semantic error highlight
    ERROR = "#e74c3c"

    # Semantic success highlight
    SUCCESS = "#2ecc71"

    # Canvas viewport background (default canvas backdrop)
    @classmethod
    def get_canvas_bg(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Window).name()
        return "#121212" if cls.is_dark_mode() else "#f5f5f5"

    # Active component borders/overlays
    @classmethod
    def get_box_active(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Highlight).name()
        return "#0c8ce9"

    # Inactive component borders/overlays
    @classmethod
    def get_box_inactive(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Dark).name()
        return "#7f8c8d" if cls.is_dark_mode() else "#95a5a6"

    # Hidden component outlines (translucent/faded versions)
    @classmethod
    def get_box_active_hidden(cls) -> str:
        app = _get_qapp()
        if app:
            color = app.palette().color(QPalette.ColorRole.Highlight)
            return QColor(color.red(), color.green(), color.blue(), 120).name()
        return "#3a6073" if cls.is_dark_mode() else "#88bbee"

    @classmethod
    def get_box_inactive_hidden(cls) -> str:
        app = _get_qapp()
        if app:
            color = app.palette().color(QPalette.ColorRole.Dark)
            return QColor(color.red(), color.green(), color.blue(), 120).name()
        return "#555555" if cls.is_dark_mode() else "#aaaaaa"

    # Pill overlay fills
    @classmethod
    def get_pill_bg_visible(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Base).name()
        return "#1e1e1e" if cls.is_dark_mode() else "#ffffff"

    @classmethod
    def get_pill_bg_hidden(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Button).name()
        return "#2c2c2c" if cls.is_dark_mode() else "#f0f0f0"

    # Semi-transparent overlay color for non-focused component areas
    @classmethod
    def get_mask_overlay(cls) -> QColor:
        app = _get_qapp()
        if app:
            bg = app.palette().color(QPalette.ColorRole.Window)
            return QColor(bg.red(), bg.green(), bg.blue(), 180)
        return (
            QColor(0, 0, 0, 180) if cls.is_dark_mode() else QColor(255, 255, 255, 120)
        )

    # Component overlay colors inside CutEditor
    @classmethod
    def get_cut_comp_fill(cls) -> QColor:
        app = _get_qapp()
        if app:
            color = app.palette().color(QPalette.ColorRole.Highlight)
            return QColor(color.red(), color.green(), color.blue(), 40)
        return (
            QColor(231, 76, 60, 30) if cls.is_dark_mode() else QColor(231, 76, 60, 40)
        )

    @classmethod
    def get_cut_comp_outline(cls) -> QColor:
        app = _get_qapp()
        if app:
            color = app.palette().color(QPalette.ColorRole.Highlight)
            return QColor(color.red(), color.green(), color.blue(), 150)
        return (
            QColor(231, 76, 60, 120) if cls.is_dark_mode() else QColor(231, 76, 60, 150)
        )

    # Child bounds reference lines on canvas
    @classmethod
    def get_child_bounds_overlay(cls) -> str:
        app = _get_qapp()
        if app:
            return app.palette().color(QPalette.ColorRole.Mid).name()
        return "#aaaaaa" if cls.is_dark_mode() else "#888888"


def get_ui_font(
    size: int | None = None, bold: bool = False, italic: bool = False
) -> QFont:
    """Constructs a platform-agnostic QFont using the standard system UI font family.

    If size is None, inherits the default application font size.
    """
    font = QFont()
    # Resolve the standard native system family (e.g. Segoe UI, San Francisco, etc.)
    font.setFamily(QApplication.font().family())
    if size is not None:
        font.setPointSize(size)
    font.setBold(bold)
    font.setItalic(italic)
    return font


def get_title_font() -> QFont:
    """Constructs the standard title font (18pt, bold)."""
    return get_ui_font(size=18, bold=True)


def get_header_font() -> QFont:
    """Constructs the standard section header font (10pt, bold)."""
    return get_ui_font(size=10, bold=True)


def get_body_font() -> QFont:
    """Constructs the standard body text font (9pt, normal)."""
    return get_ui_font(size=9)


def get_caption_font(italic: bool = False) -> QFont:
    """Constructs the standard caption font (8pt, optionally italic)."""
    return get_ui_font(size=8, italic=italic)


class LayoutTokens:
    """Standard spacing, padding, and layout dimension tokens."""

    MARGIN_DEFAULT = 10
    MARGIN_SM = 6
    SPACING_DEFAULT = 10
    SPACING_SM = 4


def set_widget_text_color(widget, hex_color: str | QColor):
    """Sets a widget's text/foreground color dynamically using QPalette manipulation.

    Avoids static QStyleSheets so colors adapt gracefully to theme updates.
    """
    palette = widget.palette()
    color = QColor(hex_color) if isinstance(hex_color, str) else hex_color
    palette.setColor(QPalette.ColorRole.WindowText, color)
    palette.setColor(QPalette.ColorRole.Text, color)
    palette.setColor(QPalette.ColorRole.ButtonText, color)
    widget.setPalette(palette)
