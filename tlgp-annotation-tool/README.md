# TLGP Annotation Tool

A desktop screenshot annotator for creating hierarchical TLGP screen specification documents. Built with Python, Tkinter, and Pillow.

## Setup

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
# Run the application
uv run python -m tlgp_annotation_tool

# Open with a specific screenshot
uv run python -m tlgp_annotation_tool screenshot.png

# Set a default output directory for export (skips the directory picker)
uv run python -m tlgp_annotation_tool screenshot.png -o /path/to/output
```

### Dependencies

| Package       | Purpose                              |
|---------------|--------------------------------------|
| Pillow        | Image loading, compositing, export   |
| ttkbootstrap  | Modern dark-themed Tkinter widgets   |
| tkinterdnd2   | Native drag-and-drop support         |

---

## Application Layout

```
┌────────────────────────────────────────────────────────────────┐
│  Toolbar (mode, navigation, zoom, actions, export)             │
├──────────┬───────────────────────────────┬─────────────────────┤
│  Layers  │                               │  Layer Properties   │
│ Sidebar  │        Canvas                 │  (name, coords)     │
│ (tree)   │                               │                     │
├──────────┴───────────────────────────────┴─────────────────────┤
│  Status bar (mode, depth breadcrumb)                           │
└────────────────────────────────────────────────────────────────┘
```

**Three resizable panes** separated by draggable sashes:
- **Left** — Layers sidebar (treeview of all annotation boxes)
- **Center** — Canvas (scrollable, zoomable image with annotation overlays)
- **Right** — Properties panel (name, X/Y/W/H of selected box)

---

## Core Concepts

### Annotation Boxes

Rectangular regions drawn on the screenshot. Each box has:
- A numeric **ID** (1-based, per sibling list)
- A text **label** (e.g. "Product Card", "Price Section")
- **Coordinates** (x1, y1, x2, y2) in absolute image space
- An optional list of **children** (nested boxes)

### Hierarchical Nesting (up to 3 levels)

Boxes support recursive nesting up to 3 levels deep:
- **Level 0 (Root)** — "Components" drawn on the full screenshot
- **Level 1** — "Sub-components" drawn inside a component
- **Level 2** — "Items" drawn inside a sub-component

Drill into a box to annotate its children; drill out to go back.

### Cut Lines (horizontal splitting)

Long screenshots can be split horizontally at arbitrary Y positions. Only supported at root level. When cuts are present:
- The main canvas shows segments with a **20px visual gap** between them
- Export produces **N+1 separate PNG files** (one per segment)
- Annotation boxes **cannot cross cut boundaries**

---

## Features

### Image Loading
- **File → Open image** — opens a single screenshot (PNG, JPG, JPEG, WebP)
- **File → Open session (JSON)** — reopens a previously exported session, restoring all annotations, cut lines, and metadata. Validates image dimensions against the JSON.
- **Drag-and-drop** — drop an image file onto the window to open it
- **CLI arguments** — pass image paths as arguments: `uv run python -m tlgp_annotation_tool path/to/image.png`

### Drawing & Selection
- **Draw mode (R/D)** — click-and-drag to create a new annotation box. The rubber-band rectangle snaps to image/parent boundaries.
- **Select mode (V/S)** — click to select, Shift/Ctrl-click for multi-select, click-and-drag to move. Drag handles to resize.
- **Marquee selection** — in select mode, drag on empty space to draw a selection rectangle. All intersected boxes are selected. Shift-drag to add to selection.
- **Double-click cycling** — when boxes overlap, double-click cycles through stacked boxes at the click position, selecting the next one underneath.
- **Multi-select move** — all selected boxes move together as a group, clamped within the current parent boundary.
- **Arrow key nudge** — move selected boxes by 1px (or 10px with Shift)

### Canvas Navigation
- **Pan mode (H)** — click-and-drag to scroll the canvas
- **Space-hold pan** — hold Spacebar to temporarily enter pan mode; release to return
- **Middle-mouse pan** — click-and-drag with middle mouse button to pan
- **Scroll wheel** — vertical scrolling
- **Shift + scroll wheel** — horizontal scrolling
- **Ctrl + scroll wheel** — zoom in/out at cursor position
- **Zoom buttons (+/-)** — zoom in 10% increments from toolbar or keyboard
- **Focus (F)** — smart zoom-to-fit:
  - If a box is selected → zoom to fit the selected box
  - If inside a drilled parent → zoom to fit the parent
  - Otherwise → zoom to fit the entire image

### Viewport Cropping

For large screenshots, the canvas uses **viewport cropping** for performance: only the visible portion of the image is rendered at full resolution. As you scroll or zoom, tiles are updated dynamically.

### Layers Sidebar
- **Treeview** showing all boxes in a hierarchical tree with ID and label columns
- **Drag-and-drop reordering** — drag rows to reorder boxes within the same parent. A blue drop indicator shows the target position.
- **Double-click** — drills into the clicked box (same as selecting + pressing Enter)
- **Overlap warnings** — boxes involved in sibling overlaps show a ⚠️ prefix
- **Auto-hiding scrollbar** — only appears when content exceeds the visible area
- **Multi-select** — synced with canvas selection

### Properties Panel (right)
- **Name field** — editable label for the selected box (press Enter or focus out to save, Escape to cancel)
- **Coordinate display** — read-only X, Y, W, H values. Coordinates are shown relative to the current parent when drilled in.
- Multi-selection shows count instead of individual properties.

### Label Visibility
- **Toggle (T)** — hides/shows annotation box labels and borders on the canvas to see the underlying screenshot clearly

### Overlap Detection
- Sibling boxes at the same depth **must not overlap**
- Overlapping boxes are highlighted with a warning color
- The toolbar shows "⚠️ Overlapping regions" and **disables export** until resolved

### Auto-Number
- **Edit → Auto-Number** — automatically reassigns box IDs in natural reading order (top-to-bottom rows, left-to-right within rows)
- Uses a geometry-aware algorithm with **vertical overlap ratio** clustering — boxes that share >50% vertical overlap are grouped into the same row
- Scale-independent: produces identical grouping at any nesting depth

### Undo / Redo
- **Ctrl+Z / Ctrl+Y** — undo/redo any annotation operation:
  - Box creation, deletion, move, resize
  - Renaming, reordering
  - Cut line changes
  - Screen info edits

### Cut Line Editor
- **Edit → Cut Lines** or press **C** — opens a dedicated modal dialog
- Shows the **full ungapped image** with red dashed cut lines overlaid
- **Add Cut** button → click on the image to place a new horizontal cut line
- **Drag** existing lines up/down to reposition (with minimum 50px gap enforcement)
- **Remove** button or Delete/Backspace to remove the selected line
- **Clear All** — removes all cut lines
- **OK** commits changes; **Cancel** discards them
- Cut lines are included in undo/redo history and saved in session JSON

### Context Menu (right-click)
- Available on the canvas, offering quick access to common operations for the clicked box

---

## Keyboard Shortcuts

| Shortcut             | Action                                      |
|----------------------|---------------------------------------------|
| `V` / `S`            | Select mode                                 |
| `R` / `D`            | Draw mode                                   |
| `H`                  | Pan mode                                    |
| `Space` (hold)       | Temporary pan mode                          |
| `Ctrl + Scroll`      | Zoom in / out at cursor                     |
| `Ctrl + +` / `-`     | Zoom in / out                               |
| `Shift + Scroll`     | Horizontal scroll                           |
| `F`                  | Focus target (zoom fit selected / parent)   |
| `T`                  | Toggle labels visibility                    |
| `C`                  | Open cut line editor                        |
| `Ctrl + Z`           | Undo                                        |
| `Ctrl + Y`           | Redo                                        |
| `Ctrl + S`           | Export session (JSON & PNG)                 |
| `Ctrl + A`           | Select all boxes at current depth           |
| `Delete` / `Backspace` | Delete selected boxes                     |
| `Enter`              | Drill down into selected box                |
| `Escape`             | Go back one level / Unfocus text field      |
| `Arrow keys`         | Nudge selected boxes by 1px                 |
| `Shift + Arrow keys` | Nudge selected boxes by 10px                |

---

## Export

**Ctrl+S** or **File → Export** prompts for an output directory. Inside it, a subfolder named after the screen is created containing:

### JSON Structure

```jsonc
{
  "screen_name": "Product Details Screen",
  "description": "Shows product info, pricing, and actions",
  "original_image": "/path/to/screenshot.png",
  "image_width": 1080,
  "image_height": 2400,
  "cut_lines": [800, 1600],  // optional, only if cuts exist
  "components": [
    {
      "id": 1,
      "label": "Header",
      "bounds": { "x": 0, "y": 0, "w": 1080, "h": 200 },
      "children": [
        {
          "id": 1,
          "label": "Back Button",
          "bounds": { "x": 10, "y": 10, "w": 40, "h": 40 }
          // bounds are relative to parent
        }
      ]
    }
  ]
}
```

- **Coordinates** in JSON are **relative to their parent**. Root-level boxes are relative to (0, 0). Child boxes are relative to their parent's top-left corner.

### Annotated PNG Images

- **Root level (no cuts)** — `{name}_annotated.png` with red borders and numbered pills on the full screenshot
- **Root level (with cuts)** — `{name}_annotated_part1.png`, `{name}_annotated_part2.png`, etc. Each part is an independently cropped segment.
- **Each parent with children** — `{name}_{path}_annotated.png` cropped to the parent box, showing only its immediate children

### Auto-Sizing Algorithm

Pill labels, font sizes, and border widths are **scaled proportionally by nesting depth**:
- At root level: full-size pills (30px font, 5px borders)
- At deeper levels: scaled by `parent_width / full_image_width` ratio
- This ensures that when a cropped sub-level image is **upscaled to full document width**, pills appear the same physical size across all levels
- When cuts are present, `full_img_width` is always the **original unsplit image width**, so all segment exports have consistent sizing

### Export Validation

Export is **blocked** if:
- No image is loaded
- Screen name is not set
- Any sibling boxes overlap at the same depth

---

## Architecture

```
src/tlgp_annotation_tool/
├── __main__.py            # CLI entry point
├── app.py                 # Main window, toolbar, menus, shortcuts, file I/O
├── canvas.py              # Annotation canvas (zoom, pan, draw, select, segments)
├── controller.py          # SessionController (event bus, navigation, CRUD)
├── models.py              # AnnotationBox, ScreenSession dataclasses
├── history.py             # HistoryManager (undo/redo snapshots)
├── sidebar.py             # Layers treeview sidebar (drag-reorder, sync)
├── properties.py          # Properties panel (name, coords display)
├── annotation_renderer.py # Shared PIL drawing logic (boxes, pills, font scaling)
├── exporter.py            # JSON + PNG export logic (with cut segment support)
├── layout_sort.py         # Geometry-aware auto-numbering (row clustering)
├── cut_editor.py          # Cut line editor dialog
└── dialogs.py             # Screen info and edit label dialogs
```

### Key Patterns

- **Event-driven architecture** — `SessionController` manages all state mutations and emits named events (`add`, `delete`, `rename`, `selection_change`, `navigation_change`, `cuts_change`, etc.). UI components subscribe to relevant events.
- **Absolute coordinate space** — all box coordinates are stored in absolute image pixels, regardless of nesting depth. The canvas transforms them to display coordinates via `to_canvas()` / `to_abs()`.
- **Segment offset system** — when cuts are active at root depth, a coordinate transform layer adds cumulative gap offsets to Y values. All box interactions continue operating in absolute space transparently.
- **History snapshots** — every mutation saves a deep-copy snapshot of the full session state. Undo/redo restores from these snapshots.

---

## Running Tests

```bash
uv run --with pytest pytest tests/ -v
```
