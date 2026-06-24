"""Central theme module for the annotator application.

Defines semantic color tokens, layout constants, font helpers, and a global
stylesheet. Colors resolve dynamically from the system QPalette at access time
to support light/dark mode seamlessly.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# ── Color Descriptors ─────────────────────────────────────────────────


class _PaletteColor:
    """Descriptor that resolves a QColor from the app's QPalette at access time.

    Falls back to a static hex color when no QApplication is running (e.g. in tests).
    """

    def __init__(
        self, role: QPalette.ColorRole, *, alpha: int = 255, fallback: str
    ):
        self.role = role
        self.alpha = alpha
        self.fallback = fallback

    def __get__(self, obj, objtype=None) -> QColor:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            color = QColor(app.palette().color(self.role))
            if self.alpha < 255:
                color.setAlpha(self.alpha)
            return color
        c = QColor(self.fallback)
        if self.alpha < 255:
            c.setAlpha(self.alpha)
        return c


class _StaticColor:
    """Descriptor for fixed semantic colors that don't vary by theme."""

    def __init__(self, hex_color: str):
        self._hex = hex_color

    def __get__(self, obj, objtype=None) -> QColor:
        return QColor(self._hex)


# ── Semantic Color Tokens ─────────────────────────────────────────────


class Colors:
    """Semantic color tokens. All resolve to QColor at access time.

    Access via the module-level ``colors`` singleton::

        from .theme import colors
        painter.fillRect(rect, colors.canvas_bg)
    """

    # Status
    error = _StaticColor("#e74c3c")

    # Text
    muted = _PaletteColor(QPalette.ColorRole.PlaceholderText, fallback="#888888")

    # Canvas viewport background
    canvas_bg = _PaletteColor(QPalette.ColorRole.Window, fallback="#f5f5f5")

    # Component box borders
    box_active = _PaletteColor(QPalette.ColorRole.Highlight, fallback="#0c8ce9")
    box_inactive = _PaletteColor(QPalette.ColorRole.Dark, fallback="#95a5a6")
    box_active_hidden = _PaletteColor(
        QPalette.ColorRole.Highlight, alpha=120, fallback="#88bbee"
    )
    box_inactive_hidden = _PaletteColor(
        QPalette.ColorRole.Dark, alpha=120, fallback="#aaaaaa"
    )

    # Pill overlay backgrounds
    pill_bg_visible = _PaletteColor(QPalette.ColorRole.Base, fallback="#ffffff")
    pill_bg_hidden = _PaletteColor(QPalette.ColorRole.Button, fallback="#f0f0f0")

    # Cut editor component overlays
    cut_comp_fill = _PaletteColor(
        QPalette.ColorRole.Highlight, alpha=40, fallback="#0c8ce9"
    )
    cut_comp_outline = _PaletteColor(
        QPalette.ColorRole.Highlight, alpha=150, fallback="#0c8ce9"
    )

    # Child bounds reference lines
    child_bounds = _PaletteColor(QPalette.ColorRole.Mid, fallback="#888888")


colors = Colors()


# ── Layout Constants ──────────────────────────────────────────────────

MARGIN = 10
MARGIN_SM = 6
SPACING = 10
SPACING_SM = 4


# ── Font Helpers ──────────────────────────────────────────────────────


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


# ── Widget Utilities ──────────────────────────────────────────────────


def set_widget_text_color(widget, color: str | QColor):
    """Sets a widget's text/foreground color dynamically using QPalette manipulation.

    Avoids static QStyleSheets so colors adapt gracefully to theme updates.
    """
    palette = widget.palette()
    qcolor = QColor(color) if isinstance(color, str) else color
    palette.setColor(QPalette.ColorRole.WindowText, qcolor)
    palette.setColor(QPalette.ColorRole.Text, qcolor)
    palette.setColor(QPalette.ColorRole.ButtonText, qcolor)
    widget.setPalette(palette)


# ── Global Stylesheet ────────────────────────────────────────────────


def get_application_stylesheet() -> str:
    """Returns a global stylesheet (QSS) utilizing dynamic QPalette queries

    to achieve modern styling (rounded borders, subtle hover feedback,
    and distinct splitter handles) while respecting system themes.
    """
    return """
        QPushButton {
            border: 1px solid palette(mid);
            border-radius: 4px;
            padding: 5px 12px;
            background-color: palette(button);
        }
        QPushButton:hover {
            background-color: palette(midlight);
        }
        QPushButton:pressed {
            background-color: palette(mid);
        }
        QPushButton:disabled {
            background-color: palette(window);
            color: palette(placeholder-text);
            border: 1px solid palette(midlight);
        }
        QSplitter::handle {
            background-color: palette(mid);
        }
        QSplitter::handle:horizontal {
            width: 2px;
        }
        QSplitter::handle:vertical {
            height: 2px;
        }
        #WelcomeCard {
            background-color: palette(base);
            border: 1px solid palette(mid);
            border-radius: 8px;
        }
    """
