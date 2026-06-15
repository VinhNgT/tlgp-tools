# TLGP Annotation GUI Client

A Tkinter-based desktop GUI application that provides an interactive screenshot annotator. Users can draw bounding boxes, assign hierarchical numbering (e.g. `1`, `1.1`), configure styles (such as pill corner alignments), set horizontal slice lines, and sync the workspace in real-time with the local `engine` backend.

## Overview

The GUI application uses a passive-view MVC pattern to separate layout, state synchronization, and user gestures. It supports rich features like drag-and-drop file loading, undo/redo operations, zooming/panning, and slice editing.

## Key Architecture & Components

- **`__main__.py`**: Bootstraps the application, instantiating the UIStateStore, ViewportTransformer, EngineClient, MainAppWindow, and AppController.
- **`AppController` (`controllers/controller.py`)**: The central coordinator connecting the UI actions (views) with backend synchronization (API client) and the local state store.
- **`ViewportTransformer` (`domain/transformer.py`)**: Performs bidirectional coordinate transformations between local canvas coordinates and absolute screenshot pixels to support panning and zooming.
- **`GestureInterpreter` (`views/gestures.py`)**: Intercepts mouse and keyboard inputs to handle visual box creation, box resizing, boundary clamping, and canvas selections.
- **`EngineClient` (`api_client.py`)**: Manages the connection to the backend FastAPI `engine` using WebSockets, processing incoming state updates and pushing client patches.
- **`CutEditor` (`cut_editor.py`)**: A dedicated interface to manage horizontal cut coordinates to exclude long redundant content blocks from the screenshot.
- **`MainAppWindow` (`views/app.py`)**: The top-level Tkinter window, managing sub-frames such as the sidebar, toolbars, debug logs list, and the central drawing canvas.

## Running the GUI

### CLI Command

Start the GUI client from the monorepo root:
```bash
uv run python -m gui
```

> [!NOTE]
> The GUI client requires the Annotation Engine backend to be running (`uv run python -m engine`) to persist state and process updates.

## Testing

Run the test suite covering coordinate transformers, gesture interpreters, controllers, and api clients:
```bash
uv run pytest apps/gui/tests/
```
