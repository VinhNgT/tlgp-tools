# TLGP Contracts Library

A shared workspace library containing the canonical Pydantic schemas that define the boundary contracts across `tlgp-tools` modules.

## Overview

This library serves as the **single source of truth** for data structures exchanged between the `annotator` desktop application and the `mcp-server`. By extracting these models into a shared library, both producer and consumer modules guarantee schema agreement at the type level, preventing drift.

## Core Models

All schemas are defined in `tlgp_contracts.workspace`:

- **`WorkspaceState`**: The root state object defining a revision of an annotation workspace, including screen info, the underlying image, and the component tree.
- **`Component`**: A tree node representing an individual UI component annotation with UUID-based parent/children relationships.
- **`Bounds`**: Geometric bounding box coordinates for a component, including computed edge properties (`left`, `right`, `top`, `bottom`).
- **`ImageExportManifest`**: Schema mapping definitions for the `mapping.json` file inside workspace image export ZIP archives.

## Usage

```python
from tlgp_contracts import WorkspaceState, Bounds

state = WorkspaceState(
    workspaceId="...",
    version=1,
    components={
        "uuid-1234": Component(
            id="uuid-1234",
            number="1",
            label="Button",
            bounds=Bounds(x=10, y=10, w=100, h=40)
        )
    }
)
```

## Development

This package is installed and managed automatically as a workspace member within the monorepo.

To run tests:
```bash
uv run pytest libs/contracts/
```
