"""Formatting constants from the TLGP spec (Appendix A of create-spec-doc.md).

All values are hardcoded from the reference document specification.
Changes here directly affect the generated .docx formatting.
"""

from docx.shared import Pt, Inches, RGBColor

# ============================================================
# Fonts
# ============================================================

FONT_FAMILY = "Times New Roman"
FONT_SIZE_DEFAULT = Pt(12)
FONT_SIZE_API = Pt(10.5)

# ============================================================
# Colors
# ============================================================

HEADING_COLOR = RGBColor(0x4F, 0x81, 0xBD)  # #4F81BD
BORDER_COLOR_HEX = "7F7F7F"
HEADER_BG_HEX = "F2F2F2"

# ============================================================
# Table Dimensions
# ============================================================

# Total table width: 468pt = 6.5 inches (standard page width minus margins)
TABLE_WIDTH_INCHES = Inches(6.5)

# Info Table (2×2) and Screen General Info Table (N×2)
INFO_COLS_PT = [120.0, 348.0]

# UI Elements Table (7 cols)
UI_COLS_PT = [35.0, 100.0, 57.0, 50.0, 50.0, 50.0, 126.0]

# Interaction Events Table (2 cols)
INTERACTION_COLS_PT = [164.5, 303.5]

# API Table (6 cols)
API_COLS_PT = [110.0, 108.0, 45.0, 83.0, 62.0, 60.0]

# ============================================================
# Cell Styling
# ============================================================

CELL_PAD_TOP_PT = 5
CELL_PAD_BOTTOM_PT = 5
CELL_PAD_LEFT_PT = 6
CELL_PAD_RIGHT_PT = 6

CELL_SPACE_ABOVE_PT = 3
CELL_SPACE_BELOW_PT = 3

BORDER_WIDTH_PT = 0.75

# ============================================================
# Table Headers
# ============================================================

UI_TABLE_HEADERS = [
    "STT", "Tên", "Loại Control", "Bắt buộc",
    "Độ dài tối đa", "Chỉnh sửa", "Mô tả",
]

INTERACTION_TABLE_HEADERS = [
    "Hành động của tác nhân", "Phản ứng của hệ thống",
]

API_TABLE_HEADERS = [
    "Tên tham số", "Ý nghĩa", "Bắt buộc",
    "Kiểu dữ liệu", "Giới hạn", "Giá trị mặc định",
]

# ============================================================
# Screen General Info Row Labels
# ============================================================

SCREEN_INFO_LABELS = [
    "Người thực hiện (Actor)",
    "Điều kiện đầu vào (Precondition)",
    "Điều kiện kích hoạt chức năng (Trigger)",
    "Luồng thông thường (Main flow)",
    "Điều kiện đầu ra (Post condition)",
    "Business Rule",
]
