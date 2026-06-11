"""Formatting constants loaded from spec_format.toml.

All values are read from the TOML config at import time. The TOML file
is the single source of truth for fonts, colors, table widths, headers,
and cell styling. This module re-exports the values as module-level
constants so downstream code (table_builder.py, doc_builder.py) can
import them unchanged.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from docx.shared import Inches, Pt, RGBColor

# ============================================================
# Load config
# ============================================================

_CONFIG_PATH = Path(__file__).parent / "spec_format.toml"

with _CONFIG_PATH.open("rb") as _f:
    _cfg = tomllib.load(_f)

# ============================================================
# Fonts
# ============================================================

FONT_FAMILY: str = _cfg["global"]["font_family"]
FONT_SIZE_DEFAULT: Pt = Pt(_cfg["global"]["font_size_pt"])
FONT_SIZE_API: Pt = Pt(_cfg["table"]["api"]["font_size_pt"])

# ============================================================
# Colors
# ============================================================

_heading_hex = _cfg["global"]["heading_color"].lstrip("#")
HEADING_COLOR = RGBColor(
    int(_heading_hex[0:2], 16),
    int(_heading_hex[2:4], 16),
    int(_heading_hex[4:6], 16),
)

BORDER_COLOR_HEX: str = _cfg["border"]["color"].lstrip("#")
HEADER_BG_HEX: str = _cfg["header"]["background_color"].lstrip("#")

# ============================================================
# Table Dimensions
# ============================================================

# Total table width: 468pt = 6.5 inches
TABLE_WIDTH_INCHES = Inches(6.5)

INFO_COLS_PT: list[float] = _cfg["table"]["info"]["col_widths_pt"]
UI_COLS_PT: list[float] = _cfg["table"]["ui_elements"]["col_widths_pt"]
INTERACTION_COLS_PT: list[float] = _cfg["table"]["interaction"]["col_widths_pt"]
API_COLS_PT: list[float] = _cfg["table"]["api"]["col_widths_pt"]

# ============================================================
# Cell Styling
# ============================================================

CELL_PAD_TOP_PT: int = _cfg["cell"]["padding_top_pt"]
CELL_PAD_BOTTOM_PT: int = _cfg["cell"]["padding_bottom_pt"]
CELL_PAD_LEFT_PT: int = _cfg["cell"]["padding_left_pt"]
CELL_PAD_RIGHT_PT: int = _cfg["cell"]["padding_right_pt"]

CELL_SPACE_ABOVE_PT: int = _cfg["cell"]["space_above_pt"]
CELL_SPACE_BELOW_PT: int = _cfg["cell"]["space_below_pt"]

BORDER_WIDTH_PT: float = _cfg["border"]["width_pt"]

# ============================================================
# Table Headers
# ============================================================

UI_TABLE_HEADERS: list[str] = _cfg["table"]["ui_elements"]["headers"]
INTERACTION_TABLE_HEADERS: list[str] = _cfg["table"]["interaction"]["headers"]
API_TABLE_HEADERS: list[str] = _cfg["table"]["api"]["headers"]

# ============================================================
# Screen General Info Row Labels
# ============================================================

SCREEN_INFO_LABELS: list[str] = _cfg["screen_info"]["labels"]
