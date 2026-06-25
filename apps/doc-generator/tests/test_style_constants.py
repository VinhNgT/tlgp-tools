"""Tests for formatting configuration loader."""


import pytest
from doc_generator.style_constants import StyleConfig, load_default_style


def test_load_default_style():
    """Verify that the real spec_format.toml is structurally valid."""
    style = load_default_style()
    assert style.FONT_FAMILY == "Times New Roman"
    assert style.FONT_SIZE_DEFAULT.pt == 12
    assert style.HEADING_COLOR is not None

def test_missing_key_raises_value_error(tmp_path):
    """Verify that a missing required key raises a ValueError."""
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[global]\nfont_family = 'Arial'\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        StyleConfig(bad_toml)

    assert "Missing required styling configuration key" in str(exc.value)
