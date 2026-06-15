# TLGP Models Library

A shared library containing Pydantic data models and traversal utilities representing the TLGP annotation workspace and hierarchical screen structure.

## Overview

This library is used across the entire `tlgp-tools` workspace (apps like `doc-generator`, `engine`, `gui`, and `mcp-server`, and libs like `rendering`) to provide type safety, serialization, and validation logic.

## Models

### Core Data Models (`models.core`)

- **`Bounds`**: Represents coordinate-based box dimensions:
  - `x`, `y`: Top-left coordinates.
  - `w`, `h`: Width and height (validated to be $\ge 4$ pixels).
  - Exposes property getters: `left`, `right`, `top`, `bottom`.
- **`Style`**: UI styling options (e.g. `pillCorner` location, defaulting to `"top_left"`).
- **`Visibility`**: Visual states of a component (e.g. `visible`, `locked`).
- **`Component`**: A single annotated box/element:
  - `id`: Unique UUID.
  - `number`: Structural number string (e.g. `"1.1"`).
  - `label`: Name or label of the component.
  - `parentId`: UUID of parent component, or `None`.
  - `childrenIds`: List of child component UUIDs.
  - `bounds`: Bounding box (`Bounds`).
  - `style`: Box style (`Style`).
  - `visibility`: Component visibility state (`Visibility`).
  - `metadata`: Custom key-value pairs (`dict[str, Any]`).
- **`ScreenInfo`**: General screen properties (name and description).
- **`ImageInfo`**: Associated screenshot details (filename, width, height).
- **`WorkspaceState`**: The top-level state representing the entire annotation session schema:
  - `version`, `sessionId`, `revision`, `readOnly`.
  - `screen`: `ScreenInfo`.
  - `image`: `ImageInfo` (optional).
  - `cutLines`: List of horizontal cut offsets (`list[int]`).
  - `rootComponents`: List of top-level component UUIDs.
  - `components`: Dictionary mapping UUID to `Component` objects.

### Tree Utilities (`models.tree`)

The `TreeUtils` class provides helpers to traverse and query the flat-map tree representation inside `WorkspaceState`:

- **`get_children(state, parent_id)`**: Retrieves a list of direct child components for a parent ID (or root components if `None`).
- **`walk_dfs(state, start_id)`**: A generator yielding components in depth-first order.
- **`has_descendants(state, component_id)`**: Checks whether a component contains children.

## Installation & Development

This package is installed and managed automatically as a workspace member within the monorepo.

To run tests:
```bash
uv run pytest
```
