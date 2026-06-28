# Spec Validation Guide

This guide maps 1-to-1 to the programmatic checks performed by the `doc-generator` validator. All of these rules must be satisfied to pass validation.

---

## 1-to-1 Validation Rules

### 1. Screen Root Single Definition
- **Rule:** The Screen root node (ID `"root"`) must be defined exactly once in `nodes`.
- **Failure:** Validator fails if the Screen root is missing or duplicated.

### 2. Unique Node IDs
- **Rule:** Every node in `nodes` must have a unique string/UUID ID.
- **Failure:** Validator fails if two nodes share the same ID.

### 3. Reachability & Orphan Nodes
- **Rule:** Every node must be reachable in the tree hierarchy starting from the Screen root (ID `"root"`) through `childrenIds`.
- **Warning:** Validator emits a warning if a node is defined in `nodes` but never referenced in any parent's `childrenIds`.

### 4. Cycle Detection
- **Rule:** The parent-child tree hierarchy must not contain circular references.
- **Failure:** Validator fails if a cycle is detected.

### 5. Parent-Child Reference Integrity
- **Rule:** Any ID listed in `childrenIds` must exist as a defined node in the `nodes` list.
- **Failure:** Validator fails if a parent references a non-existent child ID.

### 6. Single Parent Constraint
- **Rule:** A node can have at most one parent. 
- **Failure:** Validator fails if a child ID is listed in the `childrenIds` of multiple parent nodes.

### 7. Image File Existence
- **Rule:** Every image filename in `annotatedImages` and `rawImage` must exist physically on disk in the export path (unless image checks are skipped).
- **Failure:** Validator fails if any referenced image file is missing.

### 8. Container Children Requirement
- **Rule:** The Screen and any non-leaf Component container must have at least one child node listed in `childrenIds`.
- **Failure:** Validator fails if a container node has no children.

### 9. Non-Empty Labels
- **Rule:** The Screen, components, and elements must have non-empty, non-whitespace `label` strings.
- **Warning:** Validator emits a warning if a node has an empty label.

### 10. Complete Interactions
- **Rule:** Every interaction in the `interactions` list must contain non-empty `action` and `reaction` strings.
- **Warning:** Validator emits a warning if an interaction is empty or contains only whitespace.

### 11. 15-Unit Complexity Limit
- **Rule:** Each parent container (Screen or Component) has a strict complexity limit of 15 units.
  - **Formula:** `(Count of childrenIds * 1) + (Count of apis * 3) <= 15`
- **Failure:** Validator fails if a node's combined unit cost exceeds 15.

### 12. Leaf Node Control Types
- **Rule:** Elements with no children (leaf nodes) must have valid control types (e.g. `Button`, `Text`, `Icon`, `Image`, `TextField`, `Checkbox`, `Switch`, etc.). They must **not** be `Screen` or `Component`.
- **Failure:** Validator fails if a leaf node's control type is `Screen` or `Component`.

### 13. Leaf Node Interactions & APIs Restriction
- **Rule:** Leaf nodes must **not** define any interactions or APIs directly. All interactions and APIs must be declared on their parent component or the screen container.
- **Failure:** Validator fails if a leaf node has a non-empty `interactions` or `apis` list.

### 14. Container Node Control Types
- **Rule:** The root Screen node must have control type `Screen`. All non-leaf components must have control type `Component`.
- **Failure:** Validator fails if the root is not `Screen`, or if a container node (any component ID other than `"root"` with children) is not `Component`.

### 15. No "TODO" Placeholders
- **Rule:** No field in the specification JSON is allowed to contain the string `"TODO"`. This applies to:
  - Node `label`, `description`, and `controlType`.
  - Interaction `action` and `reaction` strings.
  - API `name` and `url`.
  - API Request/Response DTO payload field names and descriptions.
- **Failure:** Validator fails if the substring `"TODO"` is found in any of these properties.

### 16. Missing API Root Type Warnings
- **Rule:** If an API defines a list of payload fields in its `request` or `response` lists, it **must** specify the corresponding entry-point type in `requestRootType` or `responseRootType`.
- **Warning:** Validator emits a warning if payloads are defined but their root types are missing (meaning those tables will be omitted from the final `.docx` document).

