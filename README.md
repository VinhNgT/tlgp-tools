# TLGP Tools Monorepo

A `uv`-managed monorepo containing internal developer tools and helper libraries for managing, annotating, and generating TLGP screen specification documents.

## Repository Structure

The monorepo is structured into applications (`apps/`) and shared libraries (`libs/`):

### Applications (`apps/`)

| Path | Name | Description |
|:---|:---|:---|
| [`apps/gui`](file:///E:/tlgp-tools/apps/gui) | `gui` | Tkinter desktop GUI for drawing bounding boxes, setting cut lines, and marking component hierarchy. |
| [`apps/engine`](file:///E:/tlgp-tools/apps/engine) | `engine` | FastAPI backend service that manages collaborative state synchronization (via WebSockets/JSON Patches) and tree math. |
| [`apps/doc-generator`](file:///E:/tlgp-tools/apps/doc-generator) | `doc-generator` | Command-line utility to compile structured analysis data (`analysis.json`) into fully-formatted `.docx` specification documents. |
| [`apps/mcp-server`](file:///E:/tlgp-tools/apps/mcp-server) | `mcp-server` | Model Context Protocol (MCP) server wrapping the toolchain (annotator launch & document generator) for AI agents. |

### Shared Libraries (`libs/`)

| Path | Name | Description |
|:---|:---|:---|
| [`libs/models`](file:///E:/tlgp-tools/libs/models) | `models` | Pydantic schemas representing screen annotations, workspace states, and spatial tree traversal utilities (`TreeUtils`). |
| [`libs/rendering`](file:///E:/tlgp-tools/libs/rendering) | `rendering` | Drawing engine that renders annotation rectangles, custom number pills, and composite gapped images onto screenshots. |
| [`libs/logger`](file:///E:/tlgp-tools/libs/logger) | `tlgp-logger` | Centralized structured logger using `structlog` with automated formatting (JSON/Console) and unhandled exception hooks. |

---

## Setup

Ensure you have [`uv`](https://github.com/astral-sh/uv) installed. Sync the workspace dependencies from the root directory:

```bash
uv sync
```

---

## Usage

### 1. Launch the Annotation Tool
To use the interactive annotator, you need to start both the backend API engine and the GUI frontend client:

```bash
# Start the backend API service (runs on port 8000 by default)
uv run python -m engine

# In a separate terminal, launch the desktop GUI app
uv run python -m gui
```

### 2. Generate Specification Documents
Run the document generator directly via the workspace CLI script or Python module:

```bash
# Using the CLI script alias
uv run doc-gen analysis.json -o spec_output.docx

# Or using Python module execution
uv run python -m doc_generator analysis.json -o spec_output.docx
```

### 3. Start the MCP Server
To expose these tools to AI assistants (like the Antigravity IDE or Gemini-in-Android-Studio agents):

```bash
# Start the MCP server process over standard I/O (stdio)
uv run python -m mcp_server
```

---

## Testing & Linting

### Running Tests
To run the test suites across all packages in the workspace:

```bash
uv run pytest -v
```

### Linting & Formatting
Ruff is configured for workspace-wide linting and auto-formatting:

```bash
# Lint check the codebase
uv run ruff check

# Format source files
uv run ruff format
```
