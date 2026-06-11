"""MCP resources — reference data for the agent.

Exports text constants for the analysis.json schema documentation,
control type classification guide, and formatting spec reader.
"""

from __future__ import annotations

from pathlib import Path


# ============================================================
# analysis.json schema documentation
# ============================================================

ANALYSIS_SCHEMA_TEXT = """\
# analysis.json Schema Reference

This is the data contract between the agent's analysis work and the
doc generator. Every field maps to a specific location in the generated
.docx specification document.

## Root Fields

| Field | Type | Pre-filled by scaffold? | Description |
|---|---|---|---|
| `sectionPrefix` | `str` | ✅ (default "1.1") | Section number prefix for component headings |
| `exportDir` | `str` | ✅ | Path to the annotation export directory |
| `components` | `list[Component]` | ✅ (structure) | All annotated components |
| `screen` | `Screen` | ✅ (partial) | Screen-level metadata |
| `apis` | `list[Api]` | ❌ | API documentation from codebase analysis |

## Component Fields

| Field | Type | Pre-filled? | Description |
|---|---|---|---|
| `id` | `int` | ✅ | Annotation box ID |
| `label` | `str` | ✅ | Component name (from annotation label) |
| `description` | `str` | ❌ | Vietnamese description of the component's purpose |
| `isLeaf` | `bool` | ✅ | True if component has no children |
| `imageFile` | `str?` | ✅ | Filename of the cropped annotated image |
| `children` | `list[ChildElement]` | ✅ (structure) | UI elements inside this component |
| `interactions` | `list[Interaction]` | ❌ | User action / system reaction pairs |

## ChildElement Fields

| Field | Type | Pre-filled? | Description |
|---|---|---|---|
| `stt` | `int` | ✅ | Sequential number |
| `label` | `str` | ✅ | Element name (from annotation label) |
| `controlType` | `str` | ❌ | UI control type (Button, Text, Icon, etc.) |
| `required` | `str` | ❌ | Whether the field is required |
| `maxLength` | `str` | ❌ | Maximum input length |
| `editable` | `str` | ❌ | Whether the element is editable |
| `description` | `str` | ❌ | Vietnamese description |

## Interaction Fields

| Field | Type | Description |
|---|---|---|
| `action` | `str` | User action (e.g., "Click vào nút Back") |
| `reaction` | `str` | System response (e.g., "Quay về màn trước") |

## Screen Fields

| Field | Type | Pre-filled? | Description |
|---|---|---|---|
| `name` | `str` | ✅ | Screen name |
| `description` | `str` | ✅ | Screen description |
| `actor` | `str` | ✅ (default "Người dùng") | Who uses this screen |
| `preconditions` | `list[str]` | ❌ | Entry conditions |
| `trigger` | `str` | ❌ | What triggers the screen |
| `mainFlow` | `list[str]` | ❌ | Main user flow steps |
| `postConditions` | `list[str]` | ❌ | Exit conditions |
| `businessRules` | `list[str]` | ❌ | Business rules |
| `imageFiles` | `list[str]` | ✅ | Root-level annotated image filenames |
| `topLevelChildren` | `list[ChildElement]` | ✅ (structure) | Top-level UI elements |
| `interactions` | `list[Interaction]` | ❌ | Screen-level interactions |

## Api Fields

| Field | Type | Description |
|---|---|---|
| `number` | `int` | Sequential API number |
| `method` | `str` | HTTP method (GET, POST, PUT, DELETE) |
| `title` | `str` | Vietnamese API title |
| `url` | `str` | Endpoint path |
| `requestParams` | `list[ApiParam]` | Request parameters |
| `responseType` | `str` | Response DTO type name |
| `responseFields` | `list[ApiParam]` | Response fields |
| `subDtos` | `list[SubDto]` | Nested DTO tables |

## ApiParam Fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Parameter/field name (network key) |
| `meaning` | `str` | Vietnamese description |
| `required` | `str` | Required status |
| `dataType` | `str` | Dart type with nullability (e.g., "String?") |
| `limit` | `str` | Value constraints |
| `defaultValue` | `str` | Default value |
"""


# ============================================================
# Control types classification guide
# ============================================================

CONTROL_TYPES_TEXT = """\
# UI Control Type Classification Guide

Use this guide when analyzing annotated screenshots to determine
the correct `controlType` for each UI element.

## Control Types

| Type | Visual Indicators | Common Examples |
|---|---|---|
| `Button` | Rounded rectangle with text, solid or outlined fill, tap target | "Mua ngay", "Thêm vào giỏ", back arrow button |
| `Text` | Static label or paragraph, no interactive affordance | Titles, prices, descriptions, timestamps |
| `Icon` | Small graphical symbol, typically ≤32px, no text | Heart, share, arrow, cart, menu dots (⋮) |
| `Image` | Photo area, banner, product image, avatar, logo | Product photos, promotional banners, user avatars |
| `Component` | A nested group containing multiple sub-elements | A card with image+text+button, a header bar |
| `Tabbar` | Horizontal tab-style selector with multiple options | Category tabs, filter tabs |
| `Slide` | Dot indicators or carousel controls | Image carousel dots, page indicators |
| `TextField` | Input field with border/underline, placeholder text | Search bars, form inputs |
| `Checkbox` | Square toggle control, checked/unchecked state | Agreement checkboxes, multi-select options |
| `Switch` | Toggle slider control, on/off state | Settings toggles, feature flags |

## Classification Rules

1. If the element contains multiple distinct sub-elements → `Component`
2. If it's interactive and looks tappable → `Button` (unless it's an icon)
3. If it's a small symbol without text → `Icon`
4. If it's a photo or illustration area → `Image`
5. If it's text content without interactivity → `Text`
6. If it accepts user input → `TextField`
7. When in doubt between Button and Icon: if it has text, it's a Button

## Interaction Inference

| Control Type | Typical Interactions |
|---|---|
| `Button` | Navigate to screen, open bottom sheet, call API, submit form |
| `Icon` | Toggle state (favorite), share content, navigate, open menu |
| `Image` | Open image viewer, navigate to detail screen |
| `Component` | Scroll content, expand/collapse, navigate |
| `TextField` | Show keyboard, filter results, validate input |
| `Tabbar` | Switch displayed content category |
| `Checkbox` / `Switch` | Toggle boolean state, update preferences |
"""


# ============================================================
# Formatting spec reader
# ============================================================

def get_formatting_spec_text() -> str:
    """Read and return the spec_format.toml contents.

    The TOML file lives in the tlgp-doc-generator package. We locate it
    relative to the installed package.
    """
    try:
        from tlgp_doc_generator import style_constants  # noqa: F401
        toml_path = Path(style_constants.__file__).parent / "spec_format.toml"
        if toml_path.exists():
            return toml_path.read_text(encoding="utf-8")
    except ImportError:
        pass

    return "# spec_format.toml not found — tlgp-doc-generator may not be installed."
