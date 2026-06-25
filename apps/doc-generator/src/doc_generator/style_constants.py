"""Formatting constants loaded from spec_format.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from docx.shared import Inches, Pt, RGBColor


class StyleConfig:
    """Explicit styling configuration loaded from spec_format.toml.

    Prevents active I/O on import.
    """

    def __init__(self, cfg_path: Path):
        with cfg_path.open("rb") as f:
            cfg = tomllib.load(f)

        try:
            self.FONT_FAMILY: str = cfg["global"]["font_family"]
            self.FONT_SIZE_DEFAULT: Pt = Pt(cfg["global"]["font_size_pt"])
            self.FONT_SIZE_API: Pt = Pt(cfg["table"]["api"]["font_size_pt"])

            heading_hex = cfg["global"]["heading_color"].lstrip("#")
            self.HEADING_COLOR = RGBColor(
                int(heading_hex[0:2], 16),
                int(heading_hex[2:4], 16),
                int(heading_hex[4:6], 16),
            )

            self.BORDER_COLOR_HEX: str = cfg["border"]["color"].lstrip("#")
            self.HEADER_BG_HEX: str = cfg["header"]["background_color"].lstrip("#")

            # Total table width: 468pt = 6.5 inches
            self.TABLE_WIDTH_INCHES = Inches(6.5)

            self.INFO_COLS_PT: list[float] = cfg["table"]["info"]["col_widths_pt"]
            self.UI_COLS_PT: list[float] = cfg["table"]["ui_elements"]["col_widths_pt"]
            self.INTERACTION_COLS_PT: list[float] = cfg["table"]["interaction"][
                "col_widths_pt"
            ]
            self.API_COLS_PT: list[float] = cfg["table"]["api"]["col_widths_pt"]

            self.CELL_PAD_TOP_PT: int = cfg["cell"]["padding_top_pt"]
            self.CELL_PAD_BOTTOM_PT: int = cfg["cell"]["padding_bottom_pt"]
            self.CELL_PAD_LEFT_PT: int = cfg["cell"]["padding_left_pt"]
            self.CELL_PAD_RIGHT_PT: int = cfg["cell"]["padding_right_pt"]

            self.CELL_SPACE_ABOVE_PT: int = cfg["cell"]["space_above_pt"]
            self.CELL_SPACE_BELOW_PT: int = cfg["cell"]["space_below_pt"]

            self.BORDER_WIDTH_PT: float = cfg["border"]["width_pt"]

            self.UI_TABLE_HEADERS: list[str] = cfg["table"]["ui_elements"]["headers"]
            self.INTERACTION_TABLE_HEADERS: list[str] = cfg["table"]["interaction"][
                "headers"
            ]
            self.API_TABLE_HEADERS: list[str] = cfg["table"]["api"]["headers"]

            # Paragraph and heading spacing
            spacing = cfg["spacing"]
            self.H3_SPACE_BEFORE_PT: float = spacing["h3_space_before_pt"]
            self.H3_SPACE_AFTER_PT: float = spacing["h3_space_after_pt"]
            self.H4_SPACE_BEFORE_PT: float = spacing["h4_space_before_pt"]
            self.H4_SPACE_AFTER_PT: float = spacing["h4_space_after_pt"]
            self.NORMAL_SPACE_BEFORE_PT: float = spacing["normal_space_before_pt"]
            self.NORMAL_SPACE_AFTER_PT: float = spacing["normal_space_after_pt"]
        except KeyError as e:
            raise ValueError(f"Missing required styling configuration key: {e}") from e


def load_default_style() -> StyleConfig:
    """Helper to load standard StyleConfig from spec_format.toml."""
    cfg_path = Path(__file__).parent / "spec_format.toml"
    return StyleConfig(cfg_path)
