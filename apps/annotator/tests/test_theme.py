"""Tests for UI theme and dynamic font resolution."""

import pytest
from annotator.gui.theme import get_theme
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def test_get_theme_resolves_available_font(qapp):
    """Verify that get_theme() returns a stylesheet containing an available font family."""
    theme_stylesheet = get_theme()

    # Verify that the returned stylesheet does not contain the unresolved fallback list
    assert "font-family: \"Inter\", \"Segoe UI\", sans-serif;" not in theme_stylesheet

    # Check that the first available font from our preference list is selected
    families = QFontDatabase.families()
    selected_font = "sans-serif"
    for font in ["Inter", ".AppleSystemUIFont", "Segoe UI", "Arial"]:
        if font in families:
            selected_font = f'"{font}"'
            break

    expected_style = f"font-family: {selected_font}, sans-serif;"
    assert expected_style in theme_stylesheet
