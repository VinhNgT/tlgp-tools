# TLGP Rendering Library

A shared rendering engine providing consistent rendering of annotation boxes, text dimension measurement, level-based scaling, and image compositing for screen specifications.

## Overview

The rendering package is the single source of truth for drawing annotations onto screenshots in both the interactive Tkinter canvas preview (`gui`) and the document specification generator (`doc-generator`). It handles:
- Cross-platform font loading
- Exact text bounding box calculations across Pillow versions
- Scaling fonts, borders, and margins proportionally with hierarchy level
- Splice-line segmentation and dashed line visual gap composting

## Key Features

### Shared Annotation Drawing (`rendering.renderer`)

- **`draw_annotations_on_image`**: Renders red boundary rectangles and pill labels (e.g. `"1"`, `"1.1"`) onto a Pillow `Image` object. Box coordinate translation is adjusted dynamically by drawing offsets.
- **`composite_gapped_image`**: Slices screenshot segments at cut line boundaries and stitches them back together with a dark background and dashed line indicators to show cut locations clearly.

### Level Scaling Calculations

- **`compute_level_scale`**: Computes the scale factor at a given nesting level relative to parent width.
- **`compute_pill_font_size`**: Automatically sizes pill fonts (clamped at a minimum legibility floor of `12` pixels) depending on nesting level so that pills appear physically consistent after cropped images are upscaled in the generated documentation.
- **`compute_border_widths`**: Computes scaled border and outline widths.
- **`compute_pill_padding`**: Calculates proportional pill padding dynamically.
- **`get_pill_coords`**: Snaps the pill label to one of the four corners of its component boundary box (e.g. `top_left`, `top_right`, `bottom_left`, `bottom_right`).

### Cross-platform Font Selection

- **`get_font`**: Dynamically looks up TrueType fonts in standard system paths across macOS and Windows (`Arial Bold`, `Helvetica`, `Courier`, etc.), caching them for performance. Falls back gracefully to Pillow's default bitmap font if no TrueType fonts are found.

## Installation & Development

This package is installed and managed automatically as a workspace member within the monorepo.

To run tests:
```bash
uv run pytest
```
