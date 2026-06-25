# TLGP Tools Monorepo

A `uv`-managed monorepo containing internal developer tools and helper libraries for managing, annotating, and generating TLGP screen specification documents.

## Repository Structure

The monorepo is structured into applications (`apps/`) and shared libraries (`libs/`):

### Applications (`apps/`)

| Path | Name | Description |
|:---|:---|:---|
| `apps/annotator` | `annotator` | Desktop application containing a PySide6 GUI for drawing bounding boxes and marking component hierarchy, with an embedded FastAPI backend service for state synchronization and tool control via HTTP/WebSockets. |
| `apps/doc-generator` | `doc-generator` | Command-line utility to compile structured analysis data (`analysis.json`) into fully-formatted `.docx` specification documents. |
| `apps/mcp-server` | `mcp-server` | Model Context Protocol (MCP) server wrapping the toolchain (annotator launch & document generator) for AI agents. |

### Shared Libraries (`libs/`)

| Path | Name | Description |
|:---|:---|:---|
| `libs/contracts` | `tlgp-contracts` | Shared Pydantic schemas defining the boundary contracts between TLGP modules (annotator ↔ MCP server). |
| `libs/logger` | `tlgp-logger` | Centralized structured logger using `structlog` with automated formatting (JSON/Console) and unhandled exception hooks. |

---

## Setup

Ensure you have [`uv`](https://github.com/astral-sh/uv) installed. Sync the workspace dependencies from the root directory:

```bash
uv sync
```

---

## Usage

### 1. Launch the Annotation Tool
Start the interactive annotator. This launches a process that runs both the backend API engine (on a background thread) and the PySide6 GUI frontend:

```bash
uv run annotator
```

### 2. Generate Specification Documents
Run the document generator directly via the workspace CLI script alias:

```bash
uv run doc-gen analysis.json -o spec_output.docx
```

### 3. Start the MCP Server
To expose these tools to AI assistants (like the Antigravity IDE or Gemini-in-Android-Studio agents):

```bash
# Start the MCP server process over standard I/O (stdio)
uv run tlgp-mcp
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

---

## Development & Guidelines

This repository follows strict code quality and architectural conventions to maintain maintainability at scale.
Before contributing or spawning autonomous agents to modify this repository, please review the rules defined in the `.agents/rules/` directory:

- `.agents/rules/coding-guide.md`: Architectural guidelines, SOLID principles, testing requirements, and error-handling paradigms.
- `.agents/rules/general-guide.md`: General collaboration and developer experience guidelines.
