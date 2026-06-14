"""Shared annotation rendering logic used by both the canvas preview and the image exporter.

This module is the single source of truth for:
- Cross-platform font loading
- Text dimension measurement
- Pill font size calculation (uniform per level, consistent across upscaled exports)
- Drawing annotation boxes + number pills onto a PIL Image
"""

from models import Component
from PIL import Image, ImageDraw, ImageFont

# ── Constants ──────────────────────────────────────────────────────────

# Base font size (in pixels) used at the root level on the full-resolution image.
# At sub-levels, this is scaled down by (parent_width / full_image_width) so that
# when the cropped sub-level image is upscaled back to the full document width,
# the pills appear the same physical size as root-level pills.
BASE_FONT_SIZE = 30

# Minimum font size floor to keep pills legible even at deep nesting levels.
MIN_FONT_SIZE = 12

# Pill padding ratios relative to font size.
# At BASE_FONT_SIZE (30), these produce proportional padding.
PILL_PAD_X_RATIO = 0.7  # total horizontal padding = font_size * 0.7
PILL_PAD_Y_RATIO = 0.4  # total vertical padding  = font_size * 0.4

# Box border thickness (in image pixels).
BOX_BORDER_WIDTH = 5

# Pill outline width (in image pixels).
PILL_OUTLINE_WIDTH = 3


# Font cache mapping size to ImageFont instances.
_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def get_font(size: int):
    """Load a TrueType font with the given size, trying common Windows and macOS system paths."""
    if size in _font_cache:
        return _font_cache[size]

    font_candidates = [
        "arialbd.ttf",  # Windows Arial Bold
        "arial.ttf",  # Windows Arial Regular
        "/Library/Fonts/Arial Bold.ttf",  # macOS Arial Bold
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS Supplemental Arial Bold
        "/Library/Fonts/Arial.ttf",  # macOS Arial Regular
        "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS Supplemental Arial Regular
        "/System/Library/Fonts/Helvetica.ttc",  # macOS Helvetica
        "/System/Library/Fonts/HelveticaNeue.ttc",  # macOS Helvetica Neue
        "Courier.dfont",  # macOS Courier
    ]
    for font_name in font_candidates:
        try:
            font = ImageFont.truetype(font_name, size)
            _font_cache[size] = font
            return font
        except OSError:
            continue
    default_font = ImageFont.load_default()
    _font_cache[size] = default_font
    return default_font


# ── Text Measurement ───────────────────────────────────────────────────


def get_text_dimensions(
    draw: ImageDraw.Draw | None, text: str, font
) -> tuple[int, int, int]:
    """Safely get text width, height, and top offset across different Pillow versions.

    If `draw` is None, falls back to font-based measurement or character estimation.
    Returns (width, height, top_offset).
    """
    try:
        if draw is not None and hasattr(draw, "textbbox"):
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            return right - left, bottom - top, top
        elif hasattr(font, "getbbox"):
            left, top, right, bottom = font.getbbox(text)
            return right - left, bottom - top, top
        elif draw is not None and hasattr(draw, "textsize"):
            tw, th = draw.textsize(text, font=font)
            return tw, th, 0
    except Exception:
        pass

    # Fallback: estimate based on font size
    is_large = getattr(font, "size", 12) > 15
    char_w = 11 if is_large else 8
    char_h = 20 if is_large else 14
    return len(text) * char_w, char_h, 0


# ── Level Scaling ──────────────────────────────────────────────────────


def compute_level_scale(
    parent_comp: Component | None,
    full_img_width: int,
) -> float:
    """Compute the scale factor for a given nesting level.

    This is the ratio of the parent's width to the full image width.
    When a cropped sub-level image is upscaled to full document width,
    multiplying any dimension by this factor makes it appear the same
    physical size as the root level.

    Returns 1.0 at root level.
    """
    if parent_comp is None or full_img_width <= 0:
        return 1.0
    return parent_comp.bounds.w / full_img_width


def compute_pill_font_size(
    parent_comp: Component | None,
    full_img_width: int,
) -> int:
    """Compute the uniform pill font size for all children at a given nesting level.

    At root level (parent_comp is None): returns BASE_FONT_SIZE (30).
    At sub-levels: returns round(BASE_FONT_SIZE * scale), clamped to MIN_FONT_SIZE.
    """
    scale = compute_level_scale(parent_comp, full_img_width)
    return max(MIN_FONT_SIZE, round(BASE_FONT_SIZE * scale))


def compute_border_widths(
    parent_comp: Component | None,
    full_img_width: int,
) -> tuple[int, int]:
    """Compute scaled box border and pill outline widths for a given nesting level.

    Deeper levels get thinner lines so that when the cropped image is upscaled
    to full document width, borders appear the same thickness as root level.

    Returns (box_border_width, pill_outline_width).
    """
    scale = compute_level_scale(parent_comp, full_img_width)
    border = max(1, round(BOX_BORDER_WIDTH * scale))
    outline = max(1, round(PILL_OUTLINE_WIDTH * scale))
    return border, outline


def compute_pill_padding(font_size: int) -> tuple[int, int]:
    """Compute proportional pill padding for the given font size.

    Padding scales with font size so that the pill aspect ratio stays consistent
    across all nesting levels.

    Returns (pad_x, pad_y).
    """
    pad_x = max(4, round(font_size * PILL_PAD_X_RATIO))
    pad_y = max(2, round(font_size * PILL_PAD_Y_RATIO))
    return pad_x, pad_y


def get_pill_coords(
    left: float,
    top: float,
    right: float,
    bottom: float,
    pill_w: float,
    pill_h: float,
    pill_corner: str,
) -> tuple[float, float]:
    """Compute the pill's top-left coordinates given the box bounds and pill size.

    Snaps the pill to one of the 4 corners.
    """
    width = right - left
    height = bottom - top

    x_offset = max(0.0, width - pill_w)
    y_offset = max(0.0, height - pill_h)

    if pill_corner == "top_right":
        px = left + x_offset
        py = top
    elif pill_corner == "bottom_left":
        px = left
        py = top + y_offset
    elif pill_corner == "bottom_right":
        px = left + x_offset
        py = top + y_offset
    else:  # default: top_left
        px = left
        py = top

    return px, py


# ── Drawing ────────────────────────────────────────────────────────────


def draw_annotations_on_image(
    img: Image.Image,
    children: list[Component],
    offset_x: int,
    offset_y: int,
    parent_comp: Component | None,
    full_img_width: int,
) -> Image.Image:
    """Draw annotation boxes and number pills for immediate children onto the image.

    Args:
        img: The PIL Image to draw on (modified in place and returned).
        children: The list of child Component objects to draw.
        offset_x, offset_y: The top-left origin of `img` in absolute image coordinates.
                             Used to translate box coordinates to image-local coordinates.
        parent_comp: The parent component (None at root level). Used for pill font sizing.
        full_img_width: Width of the full stitched image. Used for pill font sizing.

    Returns:
        The modified image.
    """
    if not children:
        return img

    draw = ImageDraw.Draw(img)

    # Compute uniform dimensions for this level
    font_size = compute_pill_font_size(parent_comp, full_img_width)
    font = get_font(font_size)
    box_border_w, pill_outline_w = compute_border_widths(parent_comp, full_img_width)

    for comp in children:
        if not comp.visibility.visible:
            continue

        # Use bounds
        bx1 = comp.bounds.left - offset_x
        by1 = comp.bounds.top - offset_y
        bx2 = comp.bounds.right - offset_x
        by2 = comp.bounds.bottom - offset_y

        # Red border — scaled by level so it looks uniform after upscaling
        for i in range(box_border_w):
            draw.rectangle([bx1 + i, by1 + i, bx2 - i, by2 - i], outline="red")

        # Number pill (use string number like "1.1")
        num_str = comp.number
        tw, th, top = get_text_dimensions(draw, num_str, font)
        pad_x, pad_y = compute_pill_padding(font_size)

        pill_w = tw + pad_x
        pill_h = th + pad_y

        pill_corner = comp.style.pillCorner
        pill_x1, pill_y1 = get_pill_coords(
            bx1, by1, bx2, by2, pill_w, pill_h, pill_corner
        )
        pill_x2, pill_y2 = pill_x1 + pill_w, pill_y1 + pill_h

        draw.rectangle(
            [pill_x1, pill_y1, pill_x2, pill_y2],
            fill="white",
            outline="red",
            width=pill_outline_w,
        )
        draw.text(
            (pill_x1 + pad_x // 2, pill_y1 + pad_y // 2 - top),
            num_str,
            fill="red",
            font=font,
        )

    return img
