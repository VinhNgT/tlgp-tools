"""Figma-inspired UI theme for Annotator."""

from PySide6.QtGui import QFontDatabase

FIGMA_THEME = """
QWidget {
    background-color: #2C2D2E;
    color: #E0E0E0;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 8pt;
}

QMainWindow, QDialog {
    background-color: #2C2D2E;
}

QToolBar {
    background-color: #2C2D2E;
    border-bottom: 1px solid #383838;
    border-top: none;
    border-left: none;
    border-right: none;
    spacing: 4px;
    padding: 4px;
}

QToolBar::separator {
    background-color: #383838;
    width: 1px;
    margin: 4px 8px;
}

QSplitter::handle {
    background-color: #383838;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

QTreeView {
    background-color: #2C2D2E;
    border: none;
    outline: none;
    show-decoration-selected: 1;
}

QTreeView::item {
    padding: 4px;
    border: none;
}

QTreeView::item:selected {
    background-color: #18A0FB;
    color: #FFFFFF;
}

QTreeView::item:hover:!selected {
    background-color: #3D3E40;
}

QPushButton, QToolButton {
    background-color: #3C3D3E;
    border: 1px solid #5A5A5C;
    border-radius: 4px;
    padding: 4px 12px;
    color: #E5E5E5;
}

QPushButton:hover, QToolButton:hover {
    background-color: #4A4B4C;
    border: 1px solid #7F8082;
    color: #FFFFFF;
}

QPushButton:pressed, QToolButton:pressed {
    background-color: #18A0FB;
    border: 1px solid #18A0FB;
    color: #FFFFFF;
}

QPushButton:checked, QToolButton:checked {
    background-color: #18A0FB;
    border: 1px solid #18A0FB;
    color: #FFFFFF;
}

QPushButton:disabled, QToolButton:disabled {
    background-color: #252627;
    color: #757575;
    border: 1px solid #38383A;
}

QLineEdit, QTextEdit {
    background-color: #1A1A1B;
    border: 1px solid #48484A;
    border-radius: 4px;
    padding: 4px;
    color: #E0E0E0;
    selection-background-color: #18A0FB;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #18A0FB;
}

QLineEdit:disabled, QTextEdit:disabled {
    background-color: #222223;
    color: #7C7C7D;
    border: 1px solid #38383A;
}

QLabel {
    background-color: transparent;
}

QCheckBox {
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #383838;
    border-radius: 3px;
    background-color: #1E1E1E;
}

QCheckBox::indicator:checked {
    background-color: #18A0FB;
    border: 1px solid #18A0FB;
}

QCheckBox::indicator:hover {
    border: 1px solid #18A0FB;
}

QMenu {
    background-color: #2C2D2E;
    border: 1px solid #383838;
    border-radius: 4px;
    padding: 4px 0px;
}

QMenu::item {
    padding: 4px 24px 4px 12px;
}

QMenu::item:selected {
    background-color: #18A0FB;
    color: white;
}

QMenu::separator {
    height: 1px;
    background: #383838;
    margin: 4px 0px;
}

/* Specific component tags */
#WelcomeCard {
    background-color: #1E1E1E;
    border: 1px solid #383838;
    border-radius: 8px;
}

#AnnotationCanvas, #WelcomeScreen {
    background-color: #111111;
}
"""


def get_theme() -> str:
    """Return the Figma UI stylesheet with a dynamically resolved font family.

    Resolves the font family at runtime using the active QFontDatabase. This
    prevents Qt from warning about missing font families and avoids the startup
    overhead of populating font family aliases when a requested font is not
    installed on the system.
    """
    families = QFontDatabase.families()
    font_family = "sans-serif"
    for font in ["Inter", ".AppleSystemUIFont", "Segoe UI", "Arial"]:
        if font in families:
            font_family = f'"{font}"'
            break

    return FIGMA_THEME.replace(
        'font-family: "Inter", "Segoe UI", sans-serif;',
        f"font-family: {font_family}, sans-serif;",
    )
