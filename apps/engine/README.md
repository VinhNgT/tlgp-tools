# TLGP Annotation Engine

A FastAPI-based backend service that manages annotation session state, handles collaborative WebSocket-based visual state syncing, and provides spatial tree computations for screen spec components.

## Overview

The engine acts as the central coordinator for the annotation workspace. It provides:
- **REST & WebSocket API**: Exposes endpoints to load workspaces, upload screenshots, export annotated packages, and stream live modifications.
- **Collaborative Syncing**: Uses JSON patches over WebSockets to sync UIState changes between the Tkinter GUI client and the backend in real-time.
- **Hierarchical Layout Math**: Implements spatial queries and structural computations (such as parent-child hit testing and boundary checking) to build a parent-child component tree out of flat coordinate boxes.
- **Robust Error Boundaries**: Translates domain-level exceptions (e.g. boundary violations, overlapping boxes) into clear client error codes.

## Project Structure

- `app.py`: FastAPI application initialization, middleware routing, and global exception handlers.
- `api.py`: API routers defining HTTP endpoints and the WebSocket state-sharing channel.
- `state.py`: Manages the in-memory `WorkspaceState` lifecycle, undo/redo stacks, and JSON patch generation/application.
- `tree_math.py`: Geometry logic for computing overlap, parent-child relationships, and hierarchical component ordering.
- `exceptions.py`: Custom workspace exceptions (e.g. `BoundaryViolationError`, `ComponentNotFoundError`).

## Running the Engine

### CLI Command

To start the engine locally in development mode:
```bash
uv run python -m engine
```
This launches a Uvicorn server listening on `127.0.0.1:8000`.

### Logging Environment

Set the `TLGP_ENV` environment variable to `"prod"` to output structured JSON logs instead of dev console logs:
```bash
$env:TLGP_ENV="prod"   # PowerShell
uv run python -m engine
```

## Testing

Run unit, WebSocket, and concurrency tests:
```bash
uv run pytest apps/engine/tests/
```
