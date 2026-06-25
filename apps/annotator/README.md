# Annotator

Desktop annotation tool for TLGP screen analysis. Users load a screenshot, draw labeled bounding boxes organized in a tree, and export for an MCP agent to consume.

## Architecture

Single-process app with two threads:

- **Main thread**: PySide6 GUI (canvas, sidebar, properties panel)
- **Server thread**: FastAPI + uvicorn (REST + WebSocket API for MCP)

Both threads share a single `WorkspaceManager` instance protected by `threading.Lock` with immutable state snapshots (copy-on-write).

```
annotator/
├── models/          # Pydantic data schemas (Bounds, Component, WorkspaceState)
├── workspace/       # Domain logic (sync, thread-safe)
│   ├── manager.py   # WorkspaceManager — threading.Lock, immutable snapshots
│   ├── ordering.py  # Reading-order sort + auto-numbering
│   └── errors.py    # WorkspaceError hierarchy
├── rendering.py     # paint_annotations() — shared by GUI canvas and API export
├── api/             # Thin FastAPI transport layer
│   ├── app.py       # create_app() factory, global error→HTTP mapping
│   └── routes.py    # REST + WebSocket routes, WebSocketBroadcaster
├── gui/             # PySide6 desktop GUI
│   ├── controller.py
│   ├── canvas.py
│   ├── gestures/    # Modular gesture handlers
│   └── ...
└── __main__.py      # Entry point — starts server thread + GUI main thread
```

## Running

```bash
uv run annotator
```

## Testing

```bash
uv run pytest apps/annotator/tests/
```
