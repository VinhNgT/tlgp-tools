# Spec Writing & Classification Guide

This guide defines the semantic rules, content guidelines, and UI classification rules for writing mobile app screen specifications.

---

## 1. Specification Writing Rules

### Rule 1: Vietnamese Language
- All component labels, UI descriptions, actions, reactions, and discrepancies must be written in Vietnamese.
- English descriptions or raw code strings in user-facing fields must be translated to professional Vietnamese.

### Rule 2: Vision-Derived Naming (No Naming Prefixes)
- Screen names and component labels from the workspace/code are suggestions only. Always derive accurate, descriptive Vietnamese labels from the visual content of the raw crop images (which are free of annotated borders, highlight overlays, and numeric IDs).
- **Do NOT include generic prefixes** like "Màn hình", "Trang", "Screen", "Page", "Component", or "Thành phần" in the node `label` (e.g. write "Cài đặt" instead of "Màn hình Cài đặt" or "Trang Cài đặt"). The document compiler automatically prepends the correct prefix ("Màn hình " or "Component ") during compilation.

### Rule 3: High-Level Description Summaries
- The node `description` must be a true high-level summary (Mô tả chung) of the component's role, function, or purpose.
- Do NOT simply re-state or list the UI elements or children inside it, as those are already automatically detailed in the detailed UI elements table in the generated document.

### Rule 4: API Placement
- Document each API under the non-leaf component that **uses** its response data to render/update the UI.
- If an API is used by multiple sibling nodes, place it on their closest common ancestor node. Do not duplicate API definitions.

### Rule 5: Source Code Discovery
- Map components, interactions, and APIs to actual widgets, controllers, or classes in the source code.
- If you cannot resolve or locate the matching source code files, you **must stop and ask the user** for help rather than making assumptions.

### Rule 6: Read-Only Annotator & REST API Bypass
- The annotator state is read-only for the agent. All drawing/annotations are done by the user in the GUI.
- Do NOT attempt to bypass the MCP server layer (e.g., using raw curl or HTTP requests) to interact with the Annotator REST API directly.

### Rule 7: Programmatic Editing Only
- Do not modify `spec.json` directly using text replacement or file writing tools. Always update node properties (labels, descriptions, control types, interactions, APIs) using the `update_spec_node` tool.


---

## 2. UI Control Type Classification Guide

### Control Types

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

### Classification Rules

1. If the element contains multiple distinct sub-elements → `Component`
2. If it's interactive and looks tappable → `Button` (unless it's an icon)
3. If it's a small symbol without text → `Icon`
4. If it's a photo or illustration area → `Image`
5. If it's text content without interactivity → `Text`
6. If it accepts user input → `TextField`
7. When in doubt between Button and Icon: if it has text, it's a Button
8. **Extensibility:** The above list of control types is not exhaustive. If a UI element does not fit into any of these standard types, you can proactively introduce/invent a new descriptive control type name (e.g., `Dropdown`, `RatingBar`, `WebView`) as long as it is not `Screen` or `Component` (which are reserved for structural nodes).

### Interaction Inference

| Control Type | Typical Interactions |
|---|---|
| `Button` | Navigate to screen, open bottom sheet, call API, submit form |
| `Icon` | Toggle state (favorite), share content, navigate, open menu |
| `Image` | Open image viewer, navigate to detail screen |
| `Component` | Scroll content, expand/collapse, navigate |
| `TextField` | Show keyboard, filter results, validate input |
| `Tabbar` | Switch displayed content category |
| `Checkbox` / `Switch` | Toggle boolean state, update preferences |

---

## 3. Screen Hierarchy & API Modeling Concepts

### Visual Containment Hierarchy (The Tree)
- **Hierarchy Philosophy:** Nodes in the spec are nested to reflect visual containment on the screen. The screen root contains major layout sections, which in turn contain smaller cards or groups, which contain the leaf elements (buttons, images, texts).
- **Logical Groups:** Group related visual elements into container components (e.g., grouping a product image, title text, and buy button under a single "Product Card" component). This keeps the screen layout structured and ensures individual component headings in the compiled document contain their respective child elements.

### API Document Modeling
- **DTO Schema Mapping:** Document the API structures using separate DTO definitions. If an API payload references a nested sub-DTO (e.g., `HotProductDto` includes a `price` of type `PriceDto`), define both DTOs as separate payloads. The compiler will render the root DTO first, followed by all other defined DTOs in order.
- **Collection (List) Mapping:** When a field is a collection (list), it is fine to write its type as a list (e.g., `List<ObjectA>`). When writing the detailed schemas for the DTO payload tables, you can ignore the `List` wrapper part and define `ObjectA` as a separate DTO payload.
- **Request vs. Response Namespace:** The request payloads and response payloads are compiled as two completely independent lists/trees. If a shared DTO (e.g., a common entity like `UserDto` or `ImageDto`) is used in both the request parameters and response data, it must be defined separately in both the `request` and `response` lists.
- **Rendering Trigger:** For the document compiler to generate parameter tables, you must declare the entry-point DTO names (`requestRootType` and `responseRootType`). If they are omitted or null, the generator assumes no structured data exists and skips compiling the tables.



