"""Central design system for the annotator application.

Defines semantic design tokens, overlay colors, and platform-agnostic
font helpers to ensure consistency and seamless light/dark mode support.
"""

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication


class ColorSystem:
    # Muted secondary text (adapts natively to active palette)
    MUTED = "palette(placeholder-text)"

    # Semantic error highlight
    ERROR = "#e74c3c"

    # Semantic success highlight
    SUCCESS = "#2ecc71"

    # Canvas viewport background (default canvas backdrop)
    CANVAS_BG = "#121212"

    # Active component borders/overlays
    BOX_ACTIVE = "#0c8ce9"
    BOX_INACTIVE = "#ff4444"

    # Hidden component outlines (translucent/faded versions)
    BOX_ACTIVE_HIDDEN = "#88bbee"
    BOX_INACTIVE_HIDDEN = "#aaaaaa"

    # Pill overlay fills
    PILL_BG_VISIBLE = "#ffffff"
    PILL_BG_HIDDEN = "#f0f0f0"

    # Semi-transparent overlay color for non-focused component areas
    MASK_OVERLAY = QColor(0, 0, 0, 150)

    # Component overlay colors inside CutEditor
    CUT_COMP_FILL = QColor(255, 0, 0, 40)
    CUT_COMP_OUTLINE = QColor(255, 0, 0, 150)

    # Child bounds reference lines on canvas
    CHILD_BOUNDS_OVERLAY = "#888888"


def get_ui_font(size: int | None = None, bold: bool = False, italic: bool = False) -> QFont:
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
