"""Tests for UI theme and dynamic font resolution."""

from annotator.gui.theme import get_theme
from PySide6.QtGui import QFontDatabase


def test_get_theme_resolves_available_font(qapp):
    """Verify that get_theme() returns a stylesheet containing an available font family."""
    theme_stylesheet = get_theme()

    # Verify that the returned stylesheet does not contain the unresolved fallback list
    assert 'font-family: "Inter", "Segoe UI", sans-serif;' not in theme_stylesheet

    # Check that the first available font from our preference list is selected
    families = QFontDatabase.families()
    selected_font = "sans-serif"
    for font in ["Inter", ".AppleSystemUIFont", "Segoe UI", "Arial"]:
        if font in families:
            selected_font = f'"{font}"'
            break

    expected_style = f"font-family: {selected_font}, sans-serif;"
    assert expected_style in theme_stylesheet


def test_theme_includes_primary_button(qapp):
    """Verify that get_theme() contains the PrimaryButton and QRadioButton selector rules."""
    theme_stylesheet = get_theme()
    assert "QToolButton#PrimaryButton" in theme_stylesheet
    assert "QPushButton#PrimaryButton" in theme_stylesheet
    assert "background-color: #18A0FB;" in theme_stylesheet
    assert "QRadioButton {" in theme_stylesheet
    assert "QRadioButton::indicator {" in theme_stylesheet
